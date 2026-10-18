"""
TRIAGE — Clinical Severity Labeling Function (Chunk 3, Part A)

Implements CONTEXT.md Section 6.3 Part A:
  - Points from NEWS2-style thresholds (Royal College of Physicians) on
    respiratory rate (rr), oxygen saturation (spo2), systolic BP (sbp),
    heart rate (hr), and consciousness (ACVPU).
  - Shock Index term (HR / SBP).
  - Age risk term.
  - ECG rhythm term (vf, vt, asystole maximal; st_elevation adds points).
  - Toxicology terms (elevated SpCO and MetHb).
  - Condition severity calibration weight so every condition's mean S0
    falls within its published expected_s0_band in CONTEXT.md Section 5.3.
  - Strictly monotonic with respect to lowering SpO2 and lowering SBP.
"""

from typing import Any, Dict, Tuple


# Expected S0 bands and calibrated condition baseline offsets from CONTEXT.md Section 5.3
CONDITION_S0_BANDS: Dict[str, Tuple[float, float]] = {
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

# Condition severity weights calibrated so mean S0 per condition lands in its expected band
CONDITION_SEVERITY_WEIGHTS: Dict[str, float] = {
    "cardiac_arrest": 56.0,
    "stemi": 46.0,
    "major_haemorrhage": 52.0,
    "severe_head_injury": 52.0,
    "stroke": 46.0,
    "resp_failure": 42.0,
    "anaphylaxis": 45.0,
    "septic_shock": 42.0,
    "ruptured_aaa": 54.0,
    "chest_trauma": 45.0,
    "co_poisoning": 38.0,
    "opioid_overdose": 36.0,
    "diabetic_emergency": 34.0,
    "severe_burns": 45.0,
    "obstetric_haemorrhage": 50.0,
    "pulmonary_embolism": 44.0,
    "status_epilepticus": 38.0,
    "gi_bleed": 41.0,
    "long_bone_fracture": 27.0,
    "minor_injury": 8.0,
}

CONSCIOUSNESS_POINTS: Dict[str, float] = {
    "alert": 0.0,
    "voice": 6.5,
    "pain": 12.0,
    "unresponsive": 18.0,
}

ECG_RHYTHM_POINTS: Dict[str, float] = {
    "sinus": 0.0,
    "sinus_tach": 2.5,
    "af": 4.5,
    "brady": 5.5,
    "vt": 15.0,
    "vf": 20.0,
    "asystole": 22.0,
}


def _score_rr(rr: float) -> float:
    """NEWS2-inspired respiratory rate points (breaths/min)."""
    if rr <= 8.0:
        return 10.0 + max(0.0, (8.0 - rr) * 0.5)
    if rr <= 11.0:
        return 3.5
    if rr <= 20.0:
        return 0.0
    if rr <= 24.0:
        return 4.5 + (rr - 20.0) * 0.5
    return 8.5 + min(6.5, (rr - 24.0) * 0.35)


def _score_spo2(spo2: float) -> float:
    """
    NEWS2 Scale 1 oxygen saturation points (%).
    Strictly non-increasing with SpO2 so lowering SpO2 NEVER lowers the score.
    """
    s = max(40.0, min(100.0, float(spo2)))
    if s >= 96.0:
        return (100.0 - s) * 0.25  # 0.0 to 1.0
    if s >= 94.0:
        return 2.5 + (96.0 - s) * 1.0  # 2.5 to 4.5
    if s >= 92.0:
        return 5.5 + (94.0 - s) * 1.5  # 5.5 to 8.5
    return 9.5 + (92.0 - s) * 0.35  # 9.5 up to 27.7


def _score_sbp(sbp: float) -> float:
    """
    NEWS2 hypotension systolic blood pressure points (mmHg).
    Strictly non-increasing with SBP so lowering SBP NEVER lowers the score.
    """
    b = max(0.0, min(240.0, float(sbp)))
    if b >= 111.0:
        return (240.0 - b) * 0.008  # 0.0 to 1.032
    if b >= 101.0:
        return 2.5 + (111.0 - b) * 0.20  # 2.5 to 4.5
    if b >= 91.0:
        return 5.5 + (101.0 - b) * 0.30  # 5.5 to 8.5
    return 9.5 + (91.0 - b) * 0.18  # 9.5 up to 25.88


def _score_hr(hr: float) -> float:
    """NEWS2-inspired heart rate points (bpm)."""
    h = max(0.0, float(hr))
    if h == 0.0:
        return 16.0
    if h <= 40.0:
        return 11.0 + (40.0 - h) * 0.1
    if h <= 50.0:
        return 4.0
    if h <= 90.0:
        return 0.0
    if h <= 110.0:
        return 3.0 + (h - 90.0) * 0.1
    if h <= 130.0:
        return 6.0 + (h - 110.0) * 0.15
    return 9.5 + min(5.5, (h - 130.0) * 0.1)


def _score_shock_index(hr: float, sbp: float) -> float:
    """
    Shock Index = HR / SBP (normal 0.5 - 0.7).
    Note: As SBP decreases, Shock Index increases, reinforcing SBP monotonicity.
    """
    safe_sbp = max(30.0, float(sbp))
    si = max(0.0, float(hr)) / safe_sbp
    if si <= 0.75:
        return 0.0
    if si <= 0.90:
        return (si - 0.75) * 8.0
    return 1.2 + min(10.8, (si - 0.90) * 8.5)


def _score_age(age: float) -> float:
    """Age vulnerability points."""
    a = max(0.0, float(age))
    if a <= 50.0:
        return 0.0
    if a <= 65.0:
        return (a - 50.0) * 0.08
    return 1.2 + min(4.8, (a - 65.0) * 0.15)


def _score_toxicology(spco: float, methb: float) -> float:
    """
    Points for carboxyhaemoglobin (SpCO %) and methaemoglobin (MetHb %).
    Standard pulse oximetry over-reads in CO poisoning, so SpCO is scored directly.
    """
    pts = 0.0
    if spco > 3.0:
        pts += min(12.0, (spco - 3.0) * 0.38)
    if methb > 1.5:
        pts += min(8.0, (methb - 1.5) * 0.75)
    return pts


def compute_severity_s0(patient: Dict[str, Any]) -> float:
    """
    Compute the ground-truth baseline severity score S0 in [0.0, 100.0]
    from a patient dictionary following CONTEXT.md Section 5.3 & 6.3 Part A.
    """
    vitals = patient.get("vitals", {})
    condition_id = str(patient.get("condition_id", "minor_injury"))
    age = float(patient.get("age", 45))

    hr = float(vitals.get("hr", 80))
    sbp = float(vitals.get("sbp", 120))
    rr = float(vitals.get("rr", 16))
    spo2 = float(vitals.get("spo2", 98))
    spco = float(vitals.get("spco", 1.0))
    methb = float(vitals.get("methb", 0.6))
    ecg_rhythm = str(vitals.get("ecg_rhythm", "sinus")).lower()
    st_elevation = bool(vitals.get("st_elevation", False))
    consciousness = str(vitals.get("consciousness", "alert")).lower()

    # Physiological components
    pts_rr = _score_rr(rr)
    pts_spo2 = _score_spo2(spo2)
    pts_sbp = _score_sbp(sbp)
    pts_hr = _score_hr(hr)
    pts_cons = CONSCIOUSNESS_POINTS.get(consciousness, 0.0)
    pts_si = _score_shock_index(hr, sbp)
    pts_age = _score_age(age)
    pts_ecg = ECG_RHYTHM_POINTS.get(ecg_rhythm, 0.0) + (6.5 if st_elevation else 0.0)
    pts_tox = _score_toxicology(spco, methb)

    physio_total = (
        pts_rr
        + pts_spo2
        + pts_sbp
        + pts_hr
        + pts_cons
        + pts_si
        + pts_age
        + pts_ecg
        + pts_tox
    )

    cond_weight = CONDITION_SEVERITY_WEIGHTS.get(condition_id, 25.0)

    # Combine condition weight and scaled physiological score
    raw_s0 = cond_weight + 0.62 * physio_total
    return round(float(max(0.0, min(100.0, raw_s0))), 2)


def score_to_category(score: float) -> int:
    """
    Map a 0-100 deterioration/severity score to NHS Ambulance Response Category 1..4
    per CONTEXT.md Section 5.3:
      - 75 and above : Category 1 (Life-threatening, mean target 7 min)
      - 50 to 74     : Category 2 (Emergency, mean target 18 min)
      - 25 to 49     : Category 3 (Urgent)
      - Below 25     : Category 4 (Less urgent)
    """
    if score >= 75.0:
        return 1
    if score >= 50.0:
        return 2
    if score >= 25.0:
        return 3
    return 4


if __name__ == "__main__":
    # Quick standalone verification of scoring.py
    sample_stemi = {
        "patient_id": "p_test_1",
        "age": 68,
        "sex": "F",
        "condition_id": "stemi",
        "vitals": {
            "hr": 125,
            "sbp": 85,
            "rr": 24,
            "spo2": 91,
            "etco2": 28,
            "spco": 2.0,
            "methb": 0.8,
            "ecg_rhythm": "sinus_tach",
            "st_elevation": True,
            "consciousness": "alert",
        },
    }
    s0 = compute_severity_s0(sample_stemi)
    cat = score_to_category(s0)
    print(f"scoring.py self-test -> STEMI S0: {s0:.1f}/100 (Category {cat})")