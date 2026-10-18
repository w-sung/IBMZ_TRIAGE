"""Focused tests for Chunk 3; do not require the actual graph or mutate other chunks."""

from __future__ import annotations

from backend.app.health.deterioration import (
    base_rate_for_condition,
    calculate_deterioration_rate,
    deterioration_at,
    severity_category,
)
from backend.app.health.model import train_severity_model
from backend.app.health.patients import make_synthetic_training_patients
from backend.app.health.scoring import CONDITION_PRIORS, model_features, score_patient


EXPECTED_BANDS = {
    "cardiac_arrest": (85, 100),
    "stemi": (60, 85),
    "major_haemorrhage": (70, 95),
    "severe_head_injury": (65, 90),
    "stroke": (50, 80),
    "resp_failure": (55, 85),
    "anaphylaxis": (60, 85),
    "septic_shock": (55, 80),
    "ruptured_aaa": (75, 95),
    "chest_trauma": (60, 85),
    "co_poisoning": (40, 75),
    "opioid_overdose": (45, 80),
    "diabetic_emergency": (35, 65),
    "severe_burns": (55, 85),
    "obstetric_haemorrhage": (65, 90),
    "pulmonary_embolism": (55, 80),
    "status_epilepticus": (45, 75),
    "gi_bleed": (45, 75),
    "long_bone_fracture": (25, 45),
    "minor_injury": (5, 20),
}


def make_patient(condition_id: str = "stemi", **overrides):
    vitals = {
        "hr": 80,
        "sbp": 120,
        "rr": 16,
        "spo2": 97,
        "etco2": 40,
        "spco": 0.0,
        "methb": 0.0,
        "ecg_rhythm": "sinus",
        "st_elevation": False,
        "consciousness": "alert",
    }
    vitals.update(overrides.pop("vitals", {}))
    return {
        "patient_id": "test",
        "age": 45,
        "sex": "U",
        "condition_id": condition_id,
        "vitals": vitals,
        **overrides,
    }


def training_fixtures():
    conditions = {key: {"id": key} for key in EXPECTED_BANDS}
    patients = [make_patient(key) for key in EXPECTED_BANDS]
    return patients, conditions


def test_reference_score_is_bounded_and_spo2_monotone():
    patient = make_patient("stemi")
    values = []
    for spo2 in (100, 98, 96, 95, 93, 91, 80, 50):
        patient["vitals"]["spo2"] = spo2
        values.append(score_patient(patient))
    assert all(0 <= value <= 100 for value in values)
    assert values == sorted(values)


def test_reference_score_is_monotone_for_hypotension():
    patient = make_patient("stemi")
    values = []
    for sbp in (240, 220, 120, 111, 110, 101, 100, 91, 90, 70, 40):
        patient["vitals"]["sbp"] = sbp
        values.append(score_patient(patient))
    assert values == sorted(values)


def test_cardiac_arrest_exceeds_minor_injury_even_for_opposite_vital_extremes():
    arrest_with_neutral_vitals = make_patient("cardiac_arrest")
    minor_with_extreme_vitals = make_patient(
        "minor_injury",
        age=100,
        vitals={
            "hr": 240,
            "sbp": 40,
            "rr": 60,
            "spo2": 50,
            "etco2": 10,
            "spco": 20.0,
            "methb": 20.0,
            "ecg_rhythm": "asystole",
            "st_elevation": True,
            "consciousness": "unresponsive",
        },
    )
    assert score_patient(arrest_with_neutral_vitals) > score_patient(minor_with_extreme_vitals)
    assert CONDITION_PRIORS["cardiac_arrest"] > CONDITION_PRIORS["minor_injury"]


def test_each_condition_reference_prior_starts_inside_context_band():
    for condition_id, (lower, upper) in EXPECTED_BANDS.items():
        score = score_patient(make_patient(condition_id))
        assert lower <= score <= upper, (condition_id, score, (lower, upper))


def test_training_data_is_deterministic_and_condition_stratified():
    patients, conditions = training_fixtures()
    first = make_synthetic_training_patients(patients, conditions, count=100, seed=11)
    second = make_synthetic_training_patients(patients, conditions, count=100, seed=11)
    assert first == second
    assert {p["condition_id"] for p in first} == set(conditions)


def test_model_predicts_bounded_monotone_spo2_and_hypotension():
    patients, conditions = training_fixtures()
    predictor, report = train_severity_model(patients, conditions, seed=42, n_samples=1000)
    assert report.training_samples == 1000
    patient = make_patient("stemi", vitals={"spo2": 96, "sbp": 110})
    baseline = predictor.predict(patient)
    patient["vitals"]["spo2"] = 90
    lower_spo2 = predictor.predict(patient)
    assert lower_spo2 >= baseline
    patient["vitals"]["spo2"] = 96
    patient["vitals"]["sbp"] = 85
    lower_sbp = predictor.predict(patient)
    assert lower_sbp >= baseline
    assert 0.0 <= baseline <= 100.0

    arrest = make_patient("cardiac_arrest")
    minor = make_patient(
        "minor_injury",
        age=100,
        vitals={
            "hr": 240,
            "sbp": 40,
            "rr": 60,
            "spo2": 50,
            "etco2": 10,
            "spco": 20.0,
            "methb": 20.0,
            "ecg_rhythm": "asystole",
            "st_elevation": True,
            "consciousness": "unresponsive",
        },
    )
    assert predictor.predict(arrest) > predictor.predict(minor)


def test_model_condition_neutral_means_fall_inside_expected_bands():
    patients, conditions = training_fixtures()
    predictor, _ = train_severity_model(patients, conditions, seed=42, n_samples=2000)
    neutral = make_patient("stemi")
    for condition_id, (lower, upper) in EXPECTED_BANDS.items():
        patient = dict(neutral, condition_id=condition_id)
        prediction = predictor.predict(patient)
        assert lower <= prediction <= upper, (condition_id, prediction, (lower, upper))


def test_deterioration_rate_uses_condition_configuration_then_fallback():
    assert base_rate_for_condition("stemi") == 1.15
    configured = {"stemi": {"rate_per_min": {"min": 0.8, "max": 1.5}}}
    assert base_rate_for_condition("stemi", configured) == 1.15
    assert base_rate_for_condition("stemi", {"stemi": {"rate_per_min": 2.2}}) == 2.2


def test_rate_increases_with_shock_low_oxygen_and_age():
    baseline = make_patient("stemi", age=40)
    rate_baseline = calculate_deterioration_rate(baseline)
    high_risk = make_patient("stemi", age=80, vitals={"hr": 140, "sbp": 80, "spo2": 80})
    assert calculate_deterioration_rate(high_risk) > rate_baseline


def test_live_deterioration_caps_at_100_and_category_mapping():
    assert deterioration_at(80, 2.0, 5.0) == 90.0
    assert deterioration_at(98, 5.0, 10.0) == 100.0
    assert severity_category(75) == 1
    assert severity_category(50) == 2
    assert severity_category(25) == 3
    assert severity_category(24.9) == 4


def test_feature_count_matches_model_contract():
    patient = make_patient()
    assert len(model_features(patient)) == 22
