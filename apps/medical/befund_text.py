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


def _lesion_sentence(
    lesion_no: int,
    dermatoscopic_features: list[str],
    clinical_assessment: str,
    malignancy_risk: str,
    locale_de: bool,
) -> str:
    features_str = _join_features(dermatoscopic_features, locale_de)
    if clinical_assessment not in CLINICAL_ASSESSMENT_LABELS:
        clinical_str = "—"
    else:
        clinical_str = (CLINICAL_ASSESSMENT_LABELS[clinical_assessment][0] if locale_de else CLINICAL_ASSESSMENT_LABELS[clinical_assessment][1]).capitalize()
    if malignancy_risk not in MALIGNANCY_RISK_LABELS:
        malignancy_str = ""
    else:
        malignancy_str = MALIGNANCY_RISK_LABELS[malignancy_risk][0] if locale_de else MALIGNANCY_RISK_LABELS[malignancy_risk][1]

    if locale_de:
        part1 = f"Läsion Nr. {lesion_no} zeigt dermatoskopisch"
        if features_str:
            part1 += f" {features_str}"
        part1 += f" und wird als {clinical_str} eingestuft."
        if malignancy_str:
            part1 += f" {malignancy_str}"
        return part1
    # EN
    part1 = f"Lesion no. {lesion_no} shows dermatoscopically"
    if features_str:
        part1 += f" {features_str}"
    part1 += f" and is assessed as {clinical_str}."
    if malignancy_str:
        part1 += f" {malignancy_str}"
    return part1


def _summary_sentence(
    lesions_with_assessments: list[tuple[int, str]],
    final_assessment: str,
    locale_de: bool,
) -> str:
    if not lesions_with_assessments:
        if final_assessment in FINAL_ASSESSMENT_LABELS:
            return (FINAL_ASSESSMENT_LABELS[final_assessment][0] if locale_de else FINAL_ASSESSMENT_LABELS[final_assessment][1])
        return ""

    if locale_de:
        intro = "Bei der Analyse der digitalen dermatoskopischen Aufnahmen zeigen sich aktuell "
        parts = []
        for no, assessment in lesions_with_assessments:
            a_label = CLINICAL_ASSESSMENT_LABELS.get(assessment, ("—", "—"))
            a_str = a_label[0]
            if assessment == "CONTROL_NEEDED":
                parts.append(f"kontrollbedürftige Hautveränderungen (Läsion Nr. {no})")
            elif assessment == "SUSPICIOUS":
                parts.append(f"eine suspekt beurteilte Läsion (Läsion Nr. {no})")
            elif assessment == "SLIGHTLY_ATYPICAL":
                parts.append(f"eine leicht atypische Läsion (Läsion Nr. {no})")
            else:
                parts.append(f"Läsion Nr. {no} (unauffällig)")
        text = intro + " sowie ".join(parts) + "."
    else:
        intro = "Analysis of the digital dermatoscopic images currently shows "
        parts = []
        for no, assessment in lesions_with_assessments:
            if assessment == "CONTROL_NEEDED":
                parts.append(f"skin changes requiring follow-up (lesion no. {no})")
            elif assessment == "SUSPICIOUS":
                parts.append(f"a lesion assessed as suspicious (lesion no. {no})")
            elif assessment == "SLIGHTLY_ATYPICAL":
                parts.append(f"a slightly atypical lesion (lesion no. {no})")
            else:
                parts.append(f"lesion no. {no} (unremarkable)")
        text = intro + " and ".join(parts) + "."
    if final_assessment in FINAL_ASSESSMENT_LABELS:
        fin = FINAL_ASSESSMENT_LABELS[final_assessment][0] if locale_de else FINAL_ASSESSMENT_LABELS[final_assessment][1]
        text += " " + fin
    return text


def generate_befund_text(medical_payload: dict[str, Any], authoring_locale: str = "de-DE") -> dict[str, Any]:
    """
    From medical_payload v1 (with lesions[].lesion_no, dermatoscopic_features, clinical_assessment, malignancy_risk)
    and optional overall final_assessment, produce:
    - lesions: list of { lesion_no, generated_text }
    - summary_generated_text: string
    Does not modify the input dict.
    """
    locale_de = _locale_is_de(authoring_locale)
    lesions_in = medical_payload.get("lesions") or []
    final_assessment = medical_payload.get("final_assessment") or "NO_HIGH_GRADE_SUSPICION"

    result_lesions: list[dict[str, Any]] = []
    lesions_for_summary: list[tuple[int, str]] = []

    for L in lesions_in:
        if not isinstance(L, dict):
            continue
        no = L.get("lesion_no")
        if no is None:
            continue
        try:
            lesion_no = int(no)
        except (TypeError, ValueError):
            continue
        features = L.get("dermatoscopic_features")
        if not isinstance(features, list):
            features = []
        clinical = L.get("clinical_assessment") or ""
        malignancy = L.get("malignancy_risk") or ""

        text = _lesion_sentence(lesion_no, features, clinical, malignancy, locale_de)
        result_lesions.append({"lesion_no": lesion_no, "generated_text": text})
        lesions_for_summary.append((lesion_no, clinical))

    summary_text = _summary_sentence(lesions_for_summary, final_assessment, locale_de)

    return {
        "lesions": result_lesions,
        "summary_generated_text": summary_text,
    }
