from __future__ import annotations

import re
import uuid

import bleach
from django.core.exceptions import ValidationError
from django.db import models
from apps.core.translation_service import db_gettext_lazy
from apps.users.models import StaffUserPreferredLocale


class TimeStampedUUIDModel(models.Model):
    """Base model with UUID key and audit timestamps."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=db_gettext_lazy("administration.field_created_at", "Created at"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=db_gettext_lazy("administration.field_updated_at", "Updated at"),
    )

    class Meta:
        abstract = True


_PLACEHOLDER_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_PLACEHOLDER_TOKEN_RE = re.compile(r"\{([a-z][a-z0-9_]*)\}")
_FORBIDDEN_PLACEHOLDER_FORMAT_RE = re.compile(
    r"%\([^)]+\)s|%s|\{[a-z][a-z0-9_]*:[^}]+\}"
)
_ANY_BRACE_TOKEN_RE = re.compile(r"\{[^{}]+\}")
_HTML_ALLOWED_TAGS = ["b", "strong", "i", "em", "br", "ul", "ol", "li", "p", "span"]
_HTML_ALLOWED_ATTRIBUTES = {"span": ["class"]}
_HTML_ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


class TranslationCategory(models.TextChoices):
    DOCTOR = "doctor", "Doctor"
    RECEPTION = "reception", "Reception"
    WAITING_ROOM = "waiting_room", "Waiting room"
    ADMINISTRATION = "administration", "Administration"
    OTHER = "other", "Other"


class TranslationKeyStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    DEPRECATED = "DEPRECATED", "Deprecated"


class TranslationKey(TimeStampedUUIDModel):
    """
    Typed translation key contract.

    Example key values:
    - doctor.rec_followup_3
    - doctor.pdf_label.summary
    """

    key = models.CharField(
        max_length=150,
        unique=True,
        verbose_name=db_gettext_lazy("administration.field_key", "Key"),
    )
    category = models.CharField(
        max_length=32,
        choices=TranslationCategory.choices,
        verbose_name=db_gettext_lazy(
            "administration.field_translation_category", "Translation category"
        ),
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name=db_gettext_lazy("administration.field_description", "Description"),
    )
    is_html_allowed = models.BooleanField(
        default=False,
        verbose_name=db_gettext_lazy(
            "administration.field_is_html_allowed", "Is html allowed"
        ),
    )
    allowed_placeholders = models.JSONField(
        default=list,
        blank=True,
        verbose_name=db_gettext_lazy(
            "administration.field_allowed_placeholders", "Allowed placeholders"
        ),
    )
    status = models.CharField(
        max_length=16,
        choices=TranslationKeyStatus.choices,
        default=TranslationKeyStatus.ACTIVE,
        verbose_name=db_gettext_lazy("administration.field_key_status", "Key status"),
    )

    def clean(self) -> None:
        super().clean()
        if not self.key or "." not in self.key:
            raise ValidationError(
                {"key": "Key must use dotted namespace, e.g. doctor.some_key."}
            )
        if not self.key.startswith(f"{self.category}."):
            raise ValidationError({"key": "Key prefix must match selected category."})
        if not isinstance(self.allowed_placeholders, list):
            raise ValidationError(
                {"allowed_placeholders": "Must be a list of placeholder names."}
            )
        invalid = [
            name
            for name in self.allowed_placeholders
            if not isinstance(name, str) or not _PLACEHOLDER_NAME_RE.match(name)
        ]
        if invalid:
            raise ValidationError(
                {
                    "allowed_placeholders": f"Invalid placeholder names: {invalid}. Use [a-z][a-z0-9_]*."
                }
            )

    class Meta:
        db_table = "translation_key"
        indexes = [
            models.Index(fields=["category", "status"]),
        ]

    def __str__(self) -> str:
        return self.key


def _extract_placeholder_names(value: str) -> tuple[set[str], bool]:
    # Escaped braces are treated as literal text and ignored in placeholder parsing.
    masked = value.replace("{{", "").replace("}}", "")
    names = set(_PLACEHOLDER_TOKEN_RE.findall(masked))
    tokens = _ANY_BRACE_TOKEN_RE.findall(masked)
    has_nonstandard_token = any(
        not _PLACEHOLDER_TOKEN_RE.fullmatch(token) for token in tokens
    )
    return names, has_nonstandard_token


class TranslationValue(TimeStampedUUIDModel):
    translation_key = models.ForeignKey(
        "core.TranslationKey",
        on_delete=models.CASCADE,
        related_name="values",
        verbose_name=db_gettext_lazy(
            "administration.field_translation_key", "Translation key"
        ),
    )
    language_code = models.CharField(
        max_length=5,
        choices=StaffUserPreferredLocale.choices,
        verbose_name=db_gettext_lazy(
            "administration.field_language_code", "Language code"
        ),
    )
    value = models.TextField(
        verbose_name=db_gettext_lazy("administration.field_value", "Value")
    )
    updated_by = models.ForeignKey(
        "users.StaffUser",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="updated_translation_values",
        verbose_name=db_gettext_lazy("administration.field_updated_by", "Updated by"),
    )

    def clean(self) -> None:
        super().clean()
        if self.language_code not in StaffUserPreferredLocale.values:
            raise ValidationError(
                {
                    "language_code": f"Allowed values: {', '.join(StaffUserPreferredLocale.values)}."
                }
            )
        if _FORBIDDEN_PLACEHOLDER_FORMAT_RE.search(self.value or ""):
            raise ValidationError(
                {
                    "value": "Only {placeholder_name} format is allowed; %s/%(name)s/format specifiers are forbidden."
                }
            )
        names, has_nonstandard_token = _extract_placeholder_names(self.value or "")
        if has_nonstandard_token:
            raise ValidationError(
                {
                    "value": "Only {placeholder_name} placeholders are allowed. Use {{ and }} for literal braces."
                }
            )
        allowed = set(self.translation_key.allowed_placeholders or [])
        unknown = sorted(names - allowed)
        if unknown:
            raise ValidationError({"value": f"Unknown placeholders: {unknown}."})
        if not self.translation_key.is_html_allowed:
            if "<" in (self.value or "") or ">" in (self.value or ""):
                raise ValidationError({"value": "HTML is not allowed for this key."})
            return
        sanitized = bleach.clean(
            self.value or "",
            tags=_HTML_ALLOWED_TAGS,
            attributes=_HTML_ALLOWED_ATTRIBUTES,
            protocols=_HTML_ALLOWED_PROTOCOLS,
            strip=True,
        )
        # Persist sanitized value so render paths do not need custom escape rules.
        self.value = sanitized

    class Meta:
        db_table = "translation_value"
        constraints = [
            models.UniqueConstraint(
                fields=["translation_key", "language_code"],
                name="translation_value_key_language_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    language_code__in=list(StaffUserPreferredLocale.values)
                ),
                name="translation_value_language_allowed",
            ),
        ]
        indexes = [
            models.Index(fields=["language_code", "updated_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.translation_key.key}:{self.language_code}"


class TranslationCacheVersion(TimeStampedUUIDModel):
    category = models.CharField(
        max_length=32,
        choices=TranslationCategory.choices,
        verbose_name=db_gettext_lazy(
            "administration.field_translation_category", "Translation category"
        ),
    )
    language_code = models.CharField(
        max_length=5,
        choices=StaffUserPreferredLocale.choices,
        verbose_name=db_gettext_lazy(
            "administration.field_language_code", "Language code"
        ),
    )
    version = models.BigIntegerField(
        default=1,
        verbose_name=db_gettext_lazy("administration.field_version", "Version"),
    )

    class Meta:
        db_table = "translation_cache_version"
        constraints = [
            models.UniqueConstraint(
                fields=["category", "language_code"],
                name="translation_cache_version_category_language_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    language_code__in=list(StaffUserPreferredLocale.values)
                ),
                name="translation_cache_version_language_allowed",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.category}:{self.language_code}:v{self.version}"
