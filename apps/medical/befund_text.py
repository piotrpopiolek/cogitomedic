"""
Generate Befund text blocks from structured medical_payload (v1).
Per lesion: dermatoscopic features + clinical assessment + malignancy risk → one sentence.
Summary: aggregate sentence from all lesions + final assessment.
Labels DE/EN from db-plan §5.2 and tworzenie_befund.txt.
"""

from __future__ import annotations

from typing import Any

# Dermatoscopic features: code -> (DE, EN)
DERMATOSCOPIC_LABELS: dict[str, tuple[str, str]] = {
    "ASYMMETRY": ("Asymmetrie", "Asymmetry"),
    "IRREGULAR_BORDER": ("Unregelmäßige Begrenzung", "Irregular border"),
    "INHOMOGENEOUS_PIGMENTATION": ("inhomogene Pigmentierung", "Inhomogeneous pigmentation"),
    "MULTICOLOR": ("Mehrfarbigkeit", "Multicolor pattern"),
    "ATYPICAL_PIGMENT_NETWORK": ("atypisches Pigmentnetz", "Atypical pigment network"),
    "IRREGULAR_GLOBULES": ("unregelmäßige Globuli", "Irregular globules"),
    "IRREGULAR_DOTS": ("unregelmäßige Punkte", "Irregular dots"),
    "STRUCTURELESS_AREAS": ("strukturlose Areale", "Structureless areas"),
    "ATYPICAL_VASCULAR_STRUCTURES": ("atypische Gefäßstrukturen", "Atypical vascular structures"),
    "REGRESSION_AREAS": ("Regressionsareale (weißlich/narbig)", "Regression areas (whitish/scar-like)"),
}

CLINICAL_ASSESSMENT_LABELS: dict[str, tuple[str, str]] = {
    "UNREMARKABLE": ("unauffällig", "unremarkable"),
    "SLIGHTLY_ATYPICAL": ("leicht atypisch", "slightly atypical"),
    "CONTROL_NEEDED": ("kontrollbedürftig", "requiring follow-up"),
    "SUSPICIOUS": ("suspekt", "suspicious"),
}

MALIGNANCY_RISK_LABELS: dict[str, tuple[str, str]] = {
    "NO_SUSPICION": (
        "Aktuell besteht kein Malignitätsverdacht.",
        "There is currently no suspicion of malignancy.",
    ),
    "LOW_SUSPICION": (
        "Es besteht ein niedriger Malignitätsverdacht.",
        "There is low suspicion of malignancy.",
    ),
    "CANNOT_EXCLUDE": (
        "Ein höhergradiger Malignitätsverdacht kann nicht sicher ausgeschlossen werden.",
        "Higher-grade malignancy cannot be reliably excluded.",
    ),
}

FINAL_ASSESSMENT_LABELS: dict[str, tuple[str, str]] = {
    "NO_HIGH_GRADE_SUSPICION": (
        "Ein höhergradiger Malignitätsverdacht besteht aktuell nicht.",
        "There is currently no high-grade suspicion of malignancy.",
    ),
    "HIGH_GRADE_CANNOT_BE_EXCLUDED": (
        "Ein höhergradiger Malignitätsverdacht kann nicht sicher ausgeschlossen werden.",
        "High-grade malignancy suspicion cannot be reliably excluded.",
    ),
}


def _locale_is_de(locale: str) -> bool:
    return (locale or "de-DE").strip().lower().startswith("de")


def _join_features(feature_codes: list[str], locale_de: bool) -> str:
    if not feature_codes:
        return ""
    labels = []
    for code in feature_codes:
        if code in DERMATOSCOPIC_LABELS:
            de, en = DERMATOSCOPIC_LABELS[code]
            labels.append(de if locale_de else en)
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    # DE: "Asymmetrie sowie eine inhomogene Pigmentierung"; EN: "Asymmetry and inhomogeneous pigmentation"
    if locale_de:
        return " sowie eine ".join(labels) if len(labels) == 2 else ", ".join(labels[:-1]) + " sowie " + labels[-1]
    return " and ".join(labels)


def _format_lesion_numbers(numbers: list[int], locale_de: bool) -> str:
    """Format lesion numbers for sentence, e.g. '2, 3' or 'Nr. 2, 3'."""
    if not numbers:
        return ""
    nums_str = ", ".join(str(n) for n in sorted(numbers))
    return f"Nr. {nums_str}" if locale_de else f"no. {nums_str}"


def _lesion_sentence(
    lesion_numbers: list[int],
    dermatoscopic_features: list[str],
    clinical_assessment: str,
    malignancy_risk: str,
    locale_de: bool,
) -> str:
    """One sentence per lesion group (Wideodermatoskop). E.g. 'Läsion Nr. 2, 3 zeigen dermatoskopisch ...'."""
    if not lesion_numbers:
        return ""
    features_str = _join_features(dermatoscopic_features, locale_de)
    if clinical_assessment not in CLINICAL_ASSESSMENT_LABELS:
        clinical_str = "—"
    else:
        clinical_str = (CLINICAL_ASSESSMENT_LABELS[clinical_assessment][0] if locale_de else CLINICAL_ASSESSMENT_LABELS[clinical_assessment][1]).capitalize()
    if malignancy_risk not in MALIGNANCY_RISK_LABELS:
        malignancy_str = ""
    else:
        malignancy_str = MALIGNANCY_RISK_LABELS[malignancy_risk][0] if locale_de else MALIGNANCY_RISK_LABELS[malignancy_risk][1]

    nums_label = _format_lesion_numbers(lesion_numbers, locale_de)
    if locale_de:
        part1 = f"Läsion {nums_label} zeigen dermatoskopisch"
        if features_str:
            part1 += f" {features_str}"
        part1 += f" und werden als {clinical_str} eingestuft."
        if malignancy_str:
            part1 += f" {malignancy_str}"
        return part1
    # EN
    part1 = f"Lesion(s) {nums_label} show dermatoscopically"
    if features_str:
        part1 += f" {features_str}"
    part1 += f" and are assessed as {clinical_str}."
    if malignancy_str:
        part1 += f" {malignancy_str}"
    return part1


def _summary_sentence(
    lesions_with_assessments: list[tuple[list[int], str]],
    final_assessment: str,
    locale_de: bool,
) -> str:
    """Summary sentence: each item is (lesion_numbers for group, clinical_assessment)."""
    if not lesions_with_assessments:
        if final_assessment in FINAL_ASSESSMENT_LABELS:
            return (FINAL_ASSESSMENT_LABELS[final_assessment][0] if locale_de else FINAL_ASSESSMENT_LABELS[final_assessment][1])
        return ""

    def nums_str(nums: list[int]) -> str:
        return ", ".join(str(n) for n in sorted(nums))

    if locale_de:
        intro = "Bei der Analyse der digitalen dermatoskopischen Aufnahmen zeigen sich aktuell "
        parts = []
        for numbers, assessment in lesions_with_assessments:
            ns = nums_str(numbers)
            if assessment == "CONTROL_NEEDED":
                parts.append(f"kontrollbedürftige Hautveränderungen (Läsion Nr. {ns})")
            elif assessment == "SUSPICIOUS":
                parts.append(f"eine suspekt beurteilte Läsion (Läsion Nr. {ns})")
            elif assessment == "SLIGHTLY_ATYPICAL":
                parts.append(f"eine leicht atypische Läsion (Läsion Nr. {ns})")
            else:
                parts.append(f"Läsion Nr. {ns} (unauffällig)")
        text = intro + " sowie ".join(parts) + "."
    else:
        intro = "Analysis of the digital dermatoscopic images currently shows "
        parts = []
        for numbers, assessment in lesions_with_assessments:
            ns = nums_str(numbers)
            if assessment == "CONTROL_NEEDED":
                parts.append(f"skin changes requiring follow-up (lesion no. {ns})")
            elif assessment == "SUSPICIOUS":
                parts.append(f"a lesion assessed as suspicious (lesion no. {ns})")
            elif assessment == "SLIGHTLY_ATYPICAL":
                parts.append(f"a slightly atypical lesion (lesion no. {ns})")
            else:
                parts.append(f"lesion no. {ns} (unremarkable)")
        text = intro + " and ".join(parts) + "."
    if final_assessment in FINAL_ASSESSMENT_LABELS:
        fin = FINAL_ASSESSMENT_LABELS[final_assessment][0] if locale_de else FINAL_ASSESSMENT_LABELS[final_assessment][1]
        text += " " + fin
    return text


def generate_befund_text(
    medical_payload: dict[str, Any],
    authoring_locale: str = "de-DE",
    template_body: str | None = None,
) -> dict[str, Any]:
    """
    From medical_payload v1 (with lesions[].lesion_numbers, dermatoscopic_features, clinical_assessment, malignancy_risk)
    and optional overall final_assessment, produce:
    - lesions: list of { lesion_numbers, generated_text }
    - summary_generated_text: string (optionally prefixed with template_body when provided)
    Does not modify the input dict.
    """
    locale_de = _locale_is_de(authoring_locale)
    lesions_in = medical_payload.get("lesions") or []
    final_assessment = medical_payload.get("final_assessment") or "NO_HIGH_GRADE_SUSPICION"

    result_lesions: list[dict[str, Any]] = []
    lesions_for_summary: list[tuple[list[int], str]] = []

    for L in lesions_in:
        if not isinstance(L, dict):
            continue
        raw_numbers = L.get("lesion_numbers")
        if raw_numbers is None:
            # Backward compat: allow single lesion_no
            no = L.get("lesion_no")
            if no is not None:
                try:
                    raw_numbers = [int(no)]
                except (TypeError, ValueError):
                    continue
        if not raw_numbers:
            continue
        try:
            lesion_numbers = [int(n) for n in raw_numbers]
        except (TypeError, ValueError):
            continue
        if not lesion_numbers:
            continue
        features = L.get("dermatoscopic_features")
        if not isinstance(features, list):
            features = []
        clinical = L.get("clinical_assessment") or ""
        malignancy = L.get("malignancy_risk") or ""

        text = _lesion_sentence(lesion_numbers, features, clinical, malignancy, locale_de)
        result_lesions.append({"lesion_numbers": lesion_numbers, "generated_text": text})
        lesions_for_summary.append((lesion_numbers, clinical))

    summary_text = _summary_sentence(lesions_for_summary, final_assessment, locale_de)
    if template_body and template_body.strip():
        summary_text = template_body.strip() + "\n\n" + summary_text

    return {
        "lesions": result_lesions,
        "summary_generated_text": summary_text,
    }
