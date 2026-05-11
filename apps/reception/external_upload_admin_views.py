"""Admin HTML hub: external-upload workflow for reception / admin / manager.

Operator mapping of HTML actions to REST endpoints lives in
``docs/manual/07-wgranie-zewnetrznego-badania.md`` (section *HTML hub a API*).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any, cast

from django import forms
from django.conf import settings
from django.contrib import admin as django_admin
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Exists, OuterRef, QuerySet
from django.http import Http404, HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.core.api_utils import get_scoped_clinic_site_ids
from apps.core.exceptions import DomainError, IdempotencyConflictError
from apps.core.staff_custom_admin import (
    ensure_clinic_site_visible_to_staff_user,
    ensure_reception_admin_manager_staff,
)
from apps.core.translation_service import resolve_other_message
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.constants import EXTERNAL_UPLOAD_HUB_QUEUE_ENTRY_LOOKBACK_DAYS
from apps.medical.models import (
    DocVersionStatus,
    ExternalPdfAttachment,
    ExternalPdfStatus,
    MedicalDocument,
    MedicalDocumentSourceType,
    MedicalDocumentVersion,
)
from apps.medical.services import (
    create_external_upload_pdf_and_bind_draft,
    get_single_medical_document_for_queue_entry,
    publish_external_upload_version,
    select_external_upload_attachment_for_draft,
    start_external_upload_revision,
)
from apps.reception.models import QueueEntry, QueueEntryStatus
from apps.users.models import StaffUserPreferredLocale

try:
    from unfold.widgets import UnfoldAdminSelectWidget
except ImportError:
    UnfoldAdminSelectWidget = forms.Select


def _external_upload_preview_pdf_url(
    request: HttpRequest, *, medical_document_id: uuid.UUID
) -> str:
    """Absolute URL for external-upload preview PDF (session cookie with API).

    Uses :setting:`EXTERNAL_UPLOAD_PREVIEW_API_BASE_URL` when set (split API/admin
    domains); otherwise ``request.build_absolute_uri`` so reverse-proxy headers
    (``X-Forwarded-Proto`` / ``Host``) apply.
    """
    path = reverse(
        "medical-documents-external-upload-preview-pdf",
        kwargs={"medical_document_id": medical_document_id},
    )
    base = (getattr(settings, "EXTERNAL_UPLOAD_PREVIEW_API_BASE_URL", "") or "").strip()
    if base:
        root = base.rstrip("/")
        sub = path if path.startswith("/") else f"/{path}"
        return f"{root}{sub}"
    return request.build_absolute_uri(path)


def _external_upload_hub_queryset(
    request: Any, *, form_status: str
) -> QuerySet[QueueEntry]:
    """Queue entries eligible for external upload (intake ready, patient contact, scope)."""
    cutoff = timezone.now().date() - timedelta(
        days=EXTERNAL_UPLOAD_HUB_QUEUE_ENTRY_LOOKBACK_DAYS
    )
    intake_statuses: tuple[str, ...]
    if form_status == "submitted":
        intake_statuses = (cast(str, IntakeStatus.SUBMITTED),)
    elif form_status == "reopened":
        intake_statuses = (cast(str, IntakeStatus.REOPENED),)
    else:
        intake_statuses = (
            cast(str, IntakeStatus.SUBMITTED),
            cast(str, IntakeStatus.REOPENED),
        )

    intake_ok = PatientIntakeForm.objects.filter(
        queue_entry_id=OuterRef("pk"),
        form_status__in=intake_statuses,
    )
    blocking_doc = Exists(
        MedicalDocument.objects.filter(
            queue_entry_id=OuterRef("pk"),
        ).exclude(source_type=MedicalDocumentSourceType.EXTERNAL_UPLOAD)
    )
    qs = (
        QueueEntry.objects.filter(daily_queue__queue_date__gte=cutoff)
        .annotate(_ok_intake=Exists(intake_ok))
        .filter(_ok_intake=True)
        .annotate(_blocking=blocking_doc)
        .filter(_blocking=False)
        .exclude(entry_status=QueueEntryStatus.CANCELLED)
        .exclude(patient__phone__isnull=True)
        .exclude(patient__phone__exact="")
        .exclude(patient__date_of_birth__isnull=True)
        .select_related("patient", "daily_queue", "daily_queue__clinic_site")
    )
    scope_ids = get_scoped_clinic_site_ids(request.user)
    if scope_ids is not None:
        qs = qs.filter(daily_queue__clinic_site_id__in=scope_ids)
    return qs.order_by("-daily_queue__queue_date", "daily_queue_id", "position_no")


def queue_entry_external_upload_entry_url(
    request: HttpRequest, queue_entry: QueueEntry
) -> str | None:
    """
    If *queue_entry* appears in the external-upload hub pick list for *request.user*,
    return the staff HTML entry URL; otherwise ``None``.

    Used from :class:`~apps.reception.admin.QueueEntryAdmin` (same eligibility rules
    as :func:`_external_upload_hub_queryset` with ``form_status="all"``). Staff who
    are not reception/admin/manager never get a link.
    """
    from apps.core.staff_custom_admin import is_reception_admin_or_manager_staff

    if not is_reception_admin_or_manager_staff(request.user):
        return None
    if (
        not _external_upload_hub_queryset(request, form_status="all")
        .filter(pk=queue_entry.pk)
        .exists()
    ):
        return None
    return reverse(
        "admin_external_upload_entry",
        kwargs={"queue_entry_id": queue_entry.pk},
    )


def _external_upload_entry_queryset(request: Any) -> QuerySet[QueueEntry]:
    """Detail lookup: any SUBMITTED or REOPENED intake (ignores hub list filter)."""
    return _external_upload_hub_queryset(request, form_status="all")


class ExternalUploadHubPickForm(forms.Form):
    queue_entry = forms.ModelChoiceField(
        queryset=QueueEntry.objects.none(),
        required=True,
        label="",
        widget=UnfoldAdminSelectWidget(attrs={"required": True}),
    )

    def __init__(
        self,
        *args: Any,
        queryset: QuerySet[QueueEntry],
        empty_label: str,
        invalid_choice_message: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        f = self.fields["queue_entry"]
        f.queryset = queryset
        f.empty_label = empty_label
        f.error_messages["invalid_choice"] = invalid_choice_message


@staff_member_required
@require_http_methods(["GET", "HEAD"])
def external_upload_admin_hub_view(request):
    if (denied := ensure_reception_admin_manager_staff(request)) is not None:
        return denied

    form_status = (request.GET.get("form_status") or "all").strip().lower()
    if form_status not in ("all", "submitted", "reopened"):
        form_status = "all"

    qs = _external_upload_hub_queryset(request, form_status=form_status)
    empty_label = resolve_other_message(
        request,
        "administration.external_upload_hub_queue_entry_empty",
        "Select value",
    )
    invalid_choice = resolve_other_message(
        request,
        "administration.external_upload_hub_invalid_queue_entry",
        "Select a valid queue entry from the list.",
    )

    raw_pick = (request.GET.get("queue_entry") or "").strip()
    raw_legacy = (request.GET.get("queue_entry_id") or "").strip()
    error_invalid = None

    if raw_pick:
        form = ExternalUploadHubPickForm(
            request.GET,
            queryset=qs,
            empty_label=empty_label,
            invalid_choice_message=invalid_choice,
        )
        if form.is_valid():
            entry = form.cleaned_data["queue_entry"]
            return HttpResponseRedirect(
                reverse(
                    "admin_external_upload_entry",
                    kwargs={"queue_entry_id": entry.pk},
                )
            )
        err = form.errors.get("queue_entry")
        if err:
            error_invalid = err[0]
    elif raw_legacy:
        try:
            qid = uuid.UUID(raw_legacy)
        except ValueError:
            error_invalid = resolve_other_message(
                request,
                "administration.paper_intake_admin_invalid_uuid",
                "Enter a valid queue entry UUID.",
            )
        else:
            try:
                legacy_entry = QueueEntry.objects.select_related("daily_queue").get(
                    pk=qid
                )
            except QueueEntry.DoesNotExist:
                raise Http404()
            if (
                denied_legacy := ensure_clinic_site_visible_to_staff_user(
                    request, legacy_entry.daily_queue.clinic_site_id
                )
            ) is not None:
                return denied_legacy
            return HttpResponseRedirect(
                reverse("admin_external_upload_entry", kwargs={"queue_entry_id": qid})
            )
        form = ExternalUploadHubPickForm(
            queryset=qs,
            empty_label=empty_label,
            invalid_choice_message=invalid_choice,
        )
    else:
        form = ExternalUploadHubPickForm(
            queryset=qs,
            empty_label=empty_label,
            invalid_choice_message=invalid_choice,
        )

    context = {
        **django_admin.site.each_context(request),
        "title": resolve_other_message(
            request,
            "administration.external_upload_hub_title",
            "External examination upload",
        ),
        "intro": resolve_other_message(
            request,
            "administration.external_upload_hub_intro",
            "Select a visit with a submitted or reopened intake. Upload a PDF, confirm identity, then publish.",
        ),
        "error_invalid": error_invalid,
        "form": form,
        "hub_queue_entries_empty": not qs.exists(),
        "form_status": form_status,
    }
    return TemplateResponse(
        request, "admin/reception/external_upload_hub.html", context
    )


def _external_upload_entry_context(*, entry: QueueEntry) -> dict[str, Any]:
    medical_document = MedicalDocument.objects.filter(queue_entry_id=entry.pk).first()
    draft: MedicalDocumentVersion | None = None
    attachments: list[ExternalPdfAttachment] = []
    if medical_document is not None:
        attachments = list(
            ExternalPdfAttachment.objects.filter(
                medical_document_id=medical_document.id,
                status__in=(ExternalPdfStatus.MATCHED, ExternalPdfStatus.ACCEPTED),
            ).order_by("-created_at")
        )
        draft = (
            MedicalDocumentVersion.objects.filter(
                medical_document_id=medical_document.id,
                version_status=DocVersionStatus.DRAFT,
            )
            .order_by("-version_no")
            .first()
        )
    intake = PatientIntakeForm.objects.filter(queue_entry_id=entry.pk).first()
    return {
        "medical_document": medical_document,
        "draft": draft,
        "intake": intake,
        "attachments": attachments,
    }


@staff_member_required
@require_http_methods(["GET", "HEAD", "POST"])
def external_upload_admin_entry_view(request, queue_entry_id: uuid.UUID):
    """Staff HTML flow for one queue entry: upload, select attachment, revision, publish.

    **Scope:** if a :class:`~apps.reception.models.QueueEntry` exists but the user's
    clinic-site scope excludes it, returns **403** (same spirit as external-upload API),
    not **404**, so UUID probing cannot distinguish out-of-scope from missing rows.

    **Upload path (``action=upload``)** calls ``create_external_upload_pdf_and_bind_draft``
    (same steps as the multipart API: document → HiDrive upload → draft bind). There is
    **no** single enclosing ``transaction.atomic``: upload is split into DB phases with
    HiDrive I/O **between** commits so a DB rollback cannot leave orphan objects in
    HiDrive (see ``apps.medical.services`` docstrings for ``_register_external_upload_pdf_pending``
    and ``upload_external_pdf_to_incoming``). Each step still uses its own short atomic
    blocks where appropriate.

    A failure **after** HiDrive marked the row ``MATCHED`` but **before** draft binding
    completes leaves a recoverable partial state (attachment listed; operator can
    ``action=select``), same as the API if those calls were separate.

    **Messages:** user-visible ``messages`` text must always come from
    ``resolve_other_message`` (including ``DomainError`` / ``IdempotencyConflictError``),
    never raw ``str(exc)`` without a key—so the template's default HTML escaping stays a
    safe backstop.
    """
    if (denied := ensure_reception_admin_manager_staff(request)) is not None:
        return denied

    try:
        scope_probe = QueueEntry.objects.select_related("daily_queue").get(
            pk=queue_entry_id
        )
    except QueueEntry.DoesNotExist:
        raise Http404()
    if (
        denied_scope := ensure_clinic_site_visible_to_staff_user(
            request, scope_probe.daily_queue.clinic_site_id
        )
    ) is not None:
        return denied_scope

    entry = get_object_or_404(
        _external_upload_entry_queryset(request),
        pk=queue_entry_id,
    )

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        try:
            if action == "upload":
                uploaded = request.FILES.get("file")
                if not uploaded:
                    messages.error(
                        request,
                        resolve_other_message(
                            request,
                            "administration.external_upload_entry_upload_missing_file",
                            "Choose a PDF file before uploading.",
                        ),
                    )
                else:
                    create_external_upload_pdf_and_bind_draft(
                        queue_entry_id=entry.id,
                        uploaded_file=uploaded,
                        actor_user_id=request.user.id,
                    )
                    messages.success(
                        request,
                        resolve_other_message(
                            request,
                            "administration.external_upload_entry_upload_success",
                            "File uploaded and linked to the draft.",
                        ),
                    )
            elif action == "select":
                raw_att = (request.POST.get("attachment_id") or "").strip()
                try:
                    att_id = uuid.UUID(raw_att)
                except ValueError:
                    messages.error(
                        request,
                        resolve_other_message(
                            request,
                            "administration.external_upload_entry_invalid_attachment",
                            "Invalid attachment selection.",
                        ),
                    )
                else:
                    doc = get_single_medical_document_for_queue_entry(
                        queue_entry_id=entry.id
                    )
                    select_external_upload_attachment_for_draft(
                        medical_document_id=doc.id,
                        attachment_id=att_id,
                        actor_user_id=request.user.id,
                    )
                    messages.success(
                        request,
                        resolve_other_message(
                            request,
                            "administration.external_upload_entry_select_success",
                            "Attachment selected for the draft.",
                        ),
                    )
            elif action == "start_revision":
                doc = get_single_medical_document_for_queue_entry(
                    queue_entry_id=entry.id
                )
                start_external_upload_revision(
                    medical_document_id=doc.id,
                    actor_user_id=request.user.id,
                )
                messages.success(
                    request,
                    resolve_other_message(
                        request,
                        "administration.external_upload_entry_revision_started",
                        "A new draft revision was started. Upload or select a PDF, then publish.",
                    ),
                )
            elif action == "publish":
                if request.POST.get("verification_ack") != "1":
                    messages.error(
                        request,
                        resolve_other_message(
                            request,
                            "administration.external_upload_entry_publish_ack_required",
                            "Confirm that patient identity matches the PDF before publishing.",
                        ),
                    )
                else:
                    locale = (request.POST.get("publish_locale") or "").strip()
                    valid_locales = {
                        code for code, _ in StaffUserPreferredLocale.choices
                    }
                    if locale not in valid_locales:
                        messages.error(
                            request,
                            resolve_other_message(
                                request,
                                "administration.external_upload_entry_publish_locale_invalid",
                                "Choose a valid publish locale.",
                            ),
                        )
                    else:
                        raw_pr = (request.POST.get("publish_request_id") or "").strip()
                        try:
                            publish_request_id = uuid.UUID(raw_pr)
                        except ValueError:
                            messages.error(
                                request,
                                resolve_other_message(
                                    request,
                                    "administration.external_upload_entry_publish_request_id_invalid",
                                    "Refresh the page and publish again (invalid publish request id).",
                                ),
                            )
                        else:
                            resend = request.POST.get("resend_sms") == "1"
                            doc = get_single_medical_document_for_queue_entry(
                                queue_entry_id=entry.id
                            )
                            publish_external_upload_version(
                                medical_document_id=doc.id,
                                publish_request_id=publish_request_id,
                                published_by_user_id=request.user.id,
                                publish_locale=locale,
                                resend_sms=resend,
                            )
                            messages.success(
                                request,
                                resolve_other_message(
                                    request,
                                    "administration.external_upload_entry_publish_success",
                                    "Publication started. PDF generation and SMS follow in the background.",
                                ),
                            )
            else:
                messages.error(
                    request,
                    resolve_other_message(
                        request,
                        "administration.staff_custom_admin_invalid_action",
                        "Invalid action.",
                    ),
                )
        except MedicalDocument.DoesNotExist:
            messages.error(
                request,
                resolve_other_message(
                    request,
                    "administration.external_upload_entry_no_document",
                    "Create the document by uploading a PDF first.",
                ),
            )
        except DomainError as exc:
            messages.error(
                request,
                resolve_other_message(
                    request,
                    exc.api_message_key or "other.domain.error",
                    str(exc),
                    **(exc.api_message_params or {}),
                ),
            )
        except IdempotencyConflictError as exc:
            messages.error(
                request,
                resolve_other_message(
                    request,
                    exc.api_message_key or "other.api.error",
                    str(exc),
                    **(exc.api_message_params or {}),
                ),
            )
        return HttpResponseRedirect(
            reverse(
                "admin_external_upload_entry",
                kwargs={"queue_entry_id": entry.id},
            )
        )

    md = MedicalDocument.objects.filter(queue_entry_id=entry.pk).first()
    wrong_source = (
        md is not None and md.source_type != MedicalDocumentSourceType.EXTERNAL_UPLOAD
    )

    ctx = _external_upload_entry_context(entry=entry)
    preview_url = None
    if (
        md
        and not wrong_source
        and md.source_type == MedicalDocumentSourceType.EXTERNAL_UPLOAD
    ):
        preview_url = _external_upload_preview_pdf_url(
            request, medical_document_id=md.id
        )

    context = {
        **django_admin.site.each_context(request),
        "title": resolve_other_message(
            request,
            "administration.external_upload_entry_title",
            "External examination upload",
        ),
        "publish_request_id": str(uuid.uuid4()),
        "entry": entry,
        "patient": entry.patient,
        "daily_queue": entry.daily_queue,
        "wrong_source": wrong_source,
        "admin_queue_entry_url": reverse(
            "admin:reception_queueentry_change", args=[entry.id]
        ),
        "preview_pdf_url": preview_url,
        "locale_choices": StaffUserPreferredLocale.choices,
        **ctx,
    }
    return TemplateResponse(
        request, "admin/reception/external_upload_entry.html", context
    )
