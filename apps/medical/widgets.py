"""
Custom admin widgets for medical app.
"""

from __future__ import annotations

import base64
import json

from django.forms import Textarea
from django.template.loader import render_to_string

from apps.medical.constants import (
    CLINICAL_ASSESSMENT_CHOICES,
    DERMATOSCOPIC_FEATURE_CHOICES,
    MALIGNANCY_RISK_CHOICES,
)

try:
    from unfold.widgets import (
        CHECKBOX_CLASSES,
        INPUT_CLASSES,
        LABEL_CLASSES,
        SELECT_CLASSES,
        TEXTAREA_CLASSES,
    )
except ImportError:
    CHECKBOX_CLASSES = INPUT_CLASSES = LABEL_CLASSES = SELECT_CLASSES = TEXTAREA_CLASSES = ()


def _join_unfold_classes(*parts: object) -> str:
    out: list[str] = []
    for p in parts:
        if isinstance(p, (list, tuple)):
            out.extend(x for x in p if x)
        elif p:
            out.append(p)
    return " ".join(out)


def _safe_json_b64(value: list) -> str:
    """Encode JSON as base64 for safe embedding in HTML/script."""
    return base64.b64encode(json.dumps(value, ensure_ascii=False).encode("utf-8")).decode("ascii")


class LesionGroupFavoritesWidget(Textarea):
    """
    Widget for DoctorTextTemplate.lesion_group_favorites.
    Renders a hidden textarea (fallback when JS off) and an Alpine.js-based
    visual editor that syncs preset list to the textarea.
    """

    template_name = "medical/widgets/lesion_group_favorites.html"

    def __init__(self, attrs=None, **kwargs):
        default_attrs = {"cols": 80, "rows": 12}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs, **kwargs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        if value is None:
            value = []
        if not isinstance(value, list):
            try:
                value = json.loads(value) if isinstance(value, str) else list(value)
            except (TypeError, ValueError):
                value = []
        value_json = json.dumps(value, ensure_ascii=False)
        context["widget"]["value"] = value
        context["widget"]["value_json"] = value_json
        context["widget"]["value_b64"] = _safe_json_b64(value)
        context["widget"]["dermatoscopic_choices"] = DERMATOSCOPIC_FEATURE_CHOICES
        context["widget"]["clinical_choices"] = CLINICAL_ASSESSMENT_CHOICES
        context["widget"]["malignancy_choices"] = MALIGNANCY_RISK_CHOICES
        context["widget"]["dermatoscopic_b64"] = _safe_json_b64([{"value": v, "label": l} for v, l in DERMATOSCOPIC_FEATURE_CHOICES])
        context["widget"]["clinical_b64"] = _safe_json_b64([{"value": v, "label": l} for v, l in CLINICAL_ASSESSMENT_CHOICES])
        context["widget"]["malignancy_b64"] = _safe_json_b64([{"value": v, "label": l} for v, l in MALIGNANCY_RISK_CHOICES])
        # Match native Unfold admin fields (bundled Tailwind tokens: base-*, font-important, etc.)
        w = context["widget"]
        w["label_class"] = _join_unfold_classes(LABEL_CLASSES)
        w["input_class"] = _join_unfold_classes(INPUT_CLASSES)
        w["select_class"] = _join_unfold_classes(SELECT_CLASSES)
        w["textarea_json_class"] = _join_unfold_classes(
            ["vLargeTextField"],
            TEXTAREA_CLASSES,
            ["font-mono", "text-sm", "mb-2"],
        )
        w["textarea_body_class"] = _join_unfold_classes(["vLargeTextField"], TEXTAREA_CLASSES)
        w["checkbox_class"] = _join_unfold_classes(CHECKBOX_CLASSES)
        w["checkbox_row_label_class"] = (
            "inline-flex items-center gap-2 text-sm font-normal "
            "text-font-default-light dark:text-font-default-dark"
        )
        w["preset_card_class"] = (
            "border border-base-200 dark:border-base-700 rounded-default p-4 "
            "bg-base-50 dark:bg-base-900/50 space-y-3"
        )
        w["preset_heading_class"] = (
            "font-semibold text-sm text-font-important-light dark:text-font-important-dark"
        )
        w["help_line_class"] = "leading-relaxed mt-2 text-xs"
        w["remove_button_class"] = (
            "text-sm font-medium text-red-600 hover:text-red-700 "
            "dark:text-red-400 dark:hover:text-red-300"
        )
        w["add_preset_button_class"] = (
            "font-medium inline-flex items-center gap-2 rounded-default justify-center whitespace-nowrap "
            "cursor-pointer px-3 py-2 border border-base-200 bg-white shadow-xs text-important "
            "dark:border-base-700 dark:bg-transparent hover:bg-base-100/80 dark:hover:bg-base-800/80"
        )
        return context

    def render(self, name, value, attrs=None, renderer=None):
        context = self.get_context(name, value, attrs or {})
        return render_to_string(self.template_name, context)
