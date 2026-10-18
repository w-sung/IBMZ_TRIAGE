"""Deterministic reference labels for TRIAGE's synthetic severity model.

This is a NEWS2-inspired *simulation label*, not a NEWS2 implementation and
not a clinically validated score. The available schema lacks temperature and
oxygen-supplementation fields, and includes additional non-NEWS2 variables.
Reference: Royal College of Physicians, NEWS2 resources:
https://www.rcp.ac.uk/resources/national-early-warning-score-news-2/

Expected S0 bands in conditions.json are used for diagnostics only. They are
not used as model input; condition-specific priors below are part of the
synthetic labelling rule.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Illustrative label-function priors, chosen to preserve the ordering of the
# condition catalogue. They are not clinical probabilities or outcome data.
# Context.md expected-S0 ranges are for post-training diagnostics only. They
# are never model features and never constrain predictions.
CONDITION_EXPECTED_BANDS: dict[str, tuple[float, float]] = {
    "cardiac_arrest": (85.0, 100.0),
    "stemi": (60.0, 85.0),
    "major_haemorrhage": (70.0, 95.0),
    "severe_head_injury": (65.0, 90.0),
    "stroke": (50.0, 80.0),
    "resp_failure": (55.0, 85.0),
    "anaphylaxis": (60.0, 85.0),
    "septic_shock": (55.0, 80.0),
    "ruptured_aaa": (75.0, 95.0),
    "chest_trauma": (60.0, 85.0),
    "co_poisoning": (40.0, 75.0),
    "opioid_overdose": (45.0, 80.0),
    "diabetic_emergency": (35.0, 65.0),
    "severe_burns": (55.0, 85.0),
    "obstetric_haemorrhage": (65.0, 90.0),
    "pulmonary_embolism": (55.0, 80.0),
    "status_epilepticus": (45.0, 75.0),
    "gi_bleed": (45.0, 75.0),
    "long_bone_fracture": (25.0, 45.0),
    "minor_injury": (5.0, 20.0),
}

CONDITION_PRIORS: dict[str, float] = {
    "cardiac_arrest": 88.0,
    "stemi": 62.0,
    "major_haemorrhage": 72.0,
    "severe_head_injury": 67.0,
    "stroke": 54.0,
    "resp_failure": 58.0,
    "anaphylaxis": 62.0,
    "septic_shock": 56.0,
    "ruptured_aaa": 77.0,
    "chest_trauma": 62.0,
    "co_poisoning": 42.0,
    "opioid_overdose": 47.0,
    "diabetic_emergency": 36.0,
    "severe_burns": 57.0,
    "obstetric_haemorrhage": 67.0,
    "pulmonary_embolism": 56.0,
    "status_epilepticus": 46.0,
    "gi_bleed": 46.0,
    "long_bone_fracture": 26.0,
    "minor_injury": 6.0,
}

# A severe but non-specialist fallback prior for an unknown future condition.
DEFAULT_CONDITION_PRIOR = 45.0
RHYTHMS = ("sinus_tach", "brady", "af", "vt", "vf", "asystole")
CONSCIOUSNESS_RISK = {
    "alert": 0.0,
    "normal": 0.0,
    "voice": 1.0,
    "verbal": 1.0,
    "confused": 1.0,
    "new_confusion": 1.0,
    "pain": 2.0,
    "unresponsive": 3.0,
}


def _as_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number and abs(number) != float("inf") else default


def patient_vitals(patient: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the documented nested vitals object, or an empty mapping."""
    value = patient.get("vitals", {})
    return value if isinstance(value, Mapping) else {}


def condition_prior(
    condition_id: str,
    conditions: Mapping[str, Mapping[str, Any]] | None = None,
) -> float:
    """Return the label-function prior; optional explicit priors override defaults.

    `severity_prior` / `base_severity` are accepted when a condition explicitly
    supplies them. The expected-S0 band is deliberately never read here.
    """
    metadata: Mapping[str, Any] = {}
    if conditions:
        candidate = conditions.get(condition_id, {})
        if isinstance(candidate, Mapping):
            metadata = candidate
    for key in ("severity_prior", "base_severity"):
        if key in metadata:
            value = _as_float(metadata.get(key), DEFAULT_CONDITION_PRIOR)
            return max(0.0, min(100.0, value))
    return CONDITION_PRIORS.get(condition_id, DEFAULT_CONDITION_PRIOR)


def _respiratory_points(rr: float) -> float:
    if rr <= 8:
        return 3.0
    if rr <= 11:
        return 1.0
    if rr <= 20:
        return 0.0
    if rr <= 24:
        return 2.0
    return 3.0


def _oxygen_points(spo2: float) -> float:
    if spo2 <= 91:
        return 3.0
    if spo2 <= 93:
        return 2.0
    if spo2 <= 95:
        return 1.0
    return 0.0


def _systolic_hypotension_points(sbp: float) -> float:
    """NEWS2-style low-BP points, kept monotone as BP falls.

    This intentionally models hypotension only. Adding the NEWS2 isolated
    high-BP flag would conflict with the project's explicit monotonicity test
    that lowering systolic BP must never lower the score.
    """
    if sbp <= 90:
        return 3.0
    if sbp <= 100:
        return 2.0
    if sbp <= 110:
        return 1.0
    return 0.0


def _heart_rate_points(hr: float) -> float:
    if hr <= 40:
        return 3.0
    if hr <= 50:
        return 1.0
    if hr <= 90:
        return 0.0
    if hr <= 110:
        return 1.0
    if hr <= 130:
        return 2.0
    return 3.0


def score_patient(
    patient: Mapping[str, Any],
    conditions: Mapping[str, Mapping[str, Any]] | None = None,
) -> float:
    """Compute the deterministic 0–100 synthetic target used to train the model.

    It combines an illustrative condition prior, NEWS2-inspired vital thresholds,
    shock index, age, ECG, end-tidal CO2 and toxicology fields. This is only a
    reproducible labelling function for generated data, not medical advice.
    """
    vitals = patient_vitals(patient)
    condition_id = str(patient.get("condition_id", "unknown"))
    age = max(0.0, min(120.0, _as_float(patient.get("age", 45), 45.0)))
    hr = max(0.0, _as_float(vitals.get("hr", 80), 80.0))
    sbp = max(1.0, _as_float(vitals.get("sbp", 120), 120.0))
    rr = max(0.0, _as_float(vitals.get("rr", 16), 16.0))
    spo2 = max(0.0, min(100.0, _as_float(vitals.get("spo2", 97), 97.0)))
    etco2 = _as_float(vitals.get("etco2", 40), 40.0)
    spco = max(0.0, _as_float(vitals.get("spco", 0), 0.0))
    methb = max(0.0, _as_float(vitals.get("methb", 0), 0.0))
    rhythm = str(vitals.get("ecg_rhythm", "sinus")).strip().lower()
    consciousness = str(vitals.get("consciousness", "alert")).strip().lower()
    st_elevation = bool(vitals.get("st_elevation", False))

    # The NEWS2 source includes temperature and oxygen-support context that the
    # current project schema does not contain. Do not present this as full NEWS2.
    physiology_points = (
        _respiratory_points(rr)
        + _oxygen_points(spo2)
        + _systolic_hypotension_points(sbp)
        + _heart_rate_points(hr)
        + CONSCIOUSNESS_RISK.get(consciousness, 1.0)
    )
    score = condition_prior(condition_id, conditions) + physiology_points * 0.5

    shock_index = hr / sbp
    score += min(6.0, max(0.0, shock_index - 0.9) * 7.0)
    if age >= 80:
        score += 3.0
    elif age >= 65:
        score += 1.5

    rhythm_points = {
        "sinus_tach": 1.5,
        "brady": 1.5,
        "af": 3.0,
        "vt": 8.0,
        "vf": 9.0,
        "asystole": 10.0,
    }
    score += rhythm_points.get(rhythm, 0.0)
    if st_elevation:
        score += 5.0

    if etco2 < 25:
        score += 3.0
    elif etco2 > 50:
        score += 2.0
    if spco >= 15:
        score += 6.0
    elif spco >= 5:
        score += 2.0
    if methb >= 10:
        score += 6.0
    elif methb >= 3:
        score += 1.5

    return round(max(0.0, min(100.0, score)), 4)


def model_features(
    patient: Mapping[str, Any],
    conditions: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[float]:
    """Build ordered, monotone risk features for HistGradientBoostingRegressor.

    All features are encoded so larger means more risk. This permits positive
    monotonic constraints and helps guarantee that a falling SpO2 or falling
    systolic BP in the hypotensive range cannot reduce a model prediction.
    """
    vitals = patient_vitals(patient)
    condition_id = str(patient.get("condition_id", "unknown"))
    age = max(0.0, min(120.0, _as_float(patient.get("age", 45), 45.0)))
    hr = max(0.0, _as_float(vitals.get("hr", 80), 80.0))
    sbp = max(1.0, _as_float(vitals.get("sbp", 120), 120.0))
    rr = max(0.0, _as_float(vitals.get("rr", 16), 16.0))
    spo2 = max(0.0, min(100.0, _as_float(vitals.get("spo2", 97), 97.0)))
    etco2 = _as_float(vitals.get("etco2", 40), 40.0)
    spco = max(0.0, _as_float(vitals.get("spco", 0), 0.0))
    methb = max(0.0, _as_float(vitals.get("methb", 0), 0.0))
    rhythm = str(vitals.get("ecg_rhythm", "sinus")).strip().lower()
    consciousness = str(vitals.get("consciousness", "alert")).strip().lower()

    features = [
        condition_prior(condition_id, conditions),
        max(0.0, age - 65.0) / 15.0,
        max(0.0, age - 80.0) / 15.0,
        max(0.0, 50.0 - hr) / 10.0,
        max(0.0, hr - 90.0) / 30.0,
        max(0.0, 111.0 - sbp) / 20.0,
        max(0.0, 12.0 - rr) / 4.0,
        max(0.0, rr - 20.0) / 10.0,
        max(0.0, 96.0 - spo2) / 5.0,
        max(0.0, 30.0 - etco2) / 10.0,
        max(0.0, etco2 - 45.0) / 15.0,
        max(0.0, (hr / sbp) - 0.9),
        max(0.0, spco - 3.0) / 12.0,
        max(0.0, methb - 2.0) / 8.0,
        1.0 if rhythm == "sinus_tach" else 0.0,
        1.0 if rhythm == "brady" else 0.0,
        1.0 if rhythm == "af" else 0.0,
        1.0 if rhythm == "vt" else 0.0,
        1.0 if rhythm == "vf" else 0.0,
        1.0 if rhythm == "asystole" else 0.0,
        1.0 if bool(vitals.get("st_elevation", False)) else 0.0,
        CONSCIOUSNESS_RISK.get(consciousness, 1.0),
    ]
    return [float(value) for value in features]


FEATURE_NAMES = (
    "condition_prior",
    "age_over_65",
    "age_over_80",
    "low_heart_rate_risk",
    "high_heart_rate_risk",
    "low_systolic_bp_risk",
    "low_respiratory_rate_risk",
    "high_respiratory_rate_risk",
    "low_spo2_risk",
    "low_etco2_risk",
    "high_etco2_risk",
    "shock_index_excess",
    "spco_risk",
    "methb_risk",
    "ecg_sinus_tach",
    "ecg_brady",
    "ecg_af",
    "ecg_vt",
    "ecg_vf",
    "ecg_asystole",
    "st_elevation",
    "consciousness_risk",
)
