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
        return context

    def render(self, name, value, attrs=None, renderer=None):
        context = self.get_context(name, value, attrs or {})
        return render_to_string(self.template_name, context)
