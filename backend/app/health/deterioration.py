"""Deterministic deterioration-rate calculation, separate from ML severity."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .scoring import patient_vitals

# Midpoints of the illustrative condition ranges in CONTEXT.md. These are
# fallbacks only; an explicit rate in data/conditions.json takes precedence.
FALLBACK_BASE_RATES: dict[str, float] = {
    "cardiac_arrest": 4.0,
    "stemi": 1.15,
    "major_haemorrhage": 2.75,
    "severe_head_injury": 1.5,
    "stroke": 1.15,
    "resp_failure": 1.7,
    "anaphylaxis": 2.5,
    "septic_shock": 0.8,
    "ruptured_aaa": 2.5,
    "chest_trauma": 2.0,
    "co_poisoning": 0.75,
    "opioid_overdose": 1.5,
    "diabetic_emergency": 0.5,
    "severe_burns": 1.15,
    "obstetric_haemorrhage": 2.0,
    "pulmonary_embolism": 1.1,
    "status_epilepticus": 1.15,
    "gi_bleed": 1.05,
    "long_bone_fracture": 0.225,
    "minor_injury": 0.025,
}


def _positive_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result or result in (float("inf"), float("-inf")) or result < 0:
        return None
    return result


def _rate_from_value(value: Any) -> float | None:
    """Accept a scalar, a [min, max] pair, or {'min': x, 'max': y}."""
    scalar = _positive_float(value)
    if scalar is not None:
        return scalar
    if isinstance(value, Mapping):
        low = None
        high = None
        for key in ("min", "minimum", "low", "min_per_min", "rate_min"):
            if key in value:
                low = _positive_float(value[key])
                break
        for key in ("max", "maximum", "high", "max_per_min", "rate_max"):
            if key in value:
                high = _positive_float(value[key])
                break
        if low is not None and high is not None:
            return (low + high) / 2.0
        if low is not None:
            return low
        if high is not None:
            return high
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        low, high = _positive_float(value[0]), _positive_float(value[1])
        if low is not None and high is not None:
            return (low + high) / 2.0
    if isinstance(value, str):
        matches = re.findall(r"\d+(?:\.\d+)?", value)
        if len(matches) >= 2:
            return (float(matches[0]) + float(matches[1])) / 2.0
        if len(matches) == 1:
            return float(matches[0])
    return None


def base_rate_for_condition(
    condition_id: str,
    conditions: Mapping[str, Mapping[str, Any]] | None = None,
) -> float:
    """Read the condition's configured rate, falling back to CONTEXT.md midpoints."""
    metadata: Mapping[str, Any] = {}
    if conditions:
        candidate = conditions.get(condition_id, {})
        if isinstance(candidate, Mapping):
            metadata = candidate

    for key in (
        "base_rate",
        "rate_per_min",
        "deterioration_rate",
        "base_deterioration_rate",
        "rate",
    ):
        if key in metadata:
            parsed = _rate_from_value(metadata[key])
            if parsed is not None:
                return parsed

    low = _positive_float(metadata.get("rate_min", metadata.get("rate_min_per_min")))
    high = _positive_float(metadata.get("rate_max", metadata.get("rate_max_per_min")))
    if low is not None and high is not None:
        return (low + high) / 2.0
    if low is not None:
        return low
    if high is not None:
        return high
    return FALLBACK_BASE_RATES.get(condition_id, 0.5)


def calculate_deterioration_rate(
    patient: Mapping[str, Any],
    conditions: Mapping[str, Mapping[str, Any]] | None = None,
) -> float:
    """Return deterministic deterioration points per simulated minute.

    rate = condition base rate × vital multiplier × age multiplier.
    The multipliers and thresholds are project assumptions, not clinical truth.
    """
    condition_id = str(patient.get("condition_id", "unknown"))
    vitals = patient_vitals(patient)
    try:
        hr = max(0.0, float(vitals.get("hr", 80)))
    except (TypeError, ValueError):
        hr = 80.0
    try:
        sbp = max(1.0, float(vitals.get("sbp", 120)))
    except (TypeError, ValueError):
        sbp = 120.0
    try:
        spo2 = min(100.0, max(0.0, float(vitals.get("spo2", 97))))
    except (TypeError, ValueError):
        spo2 = 97.0
    try:
        age = max(0.0, float(patient.get("age", 45)))
    except (TypeError, ValueError):
        age = 45.0

    shock_index = hr / sbp
    vital_multiplier = 1.0 + 0.25 * max(0.0, shock_index - 0.9)
    vital_multiplier += 0.02 * max(0.0, 94.0 - spo2)
    age_multiplier = 1.15 if age >= 80 else 1.10 if age > 65 else 1.0
    return round(
        base_rate_for_condition(condition_id, conditions)
        * vital_multiplier
        * age_multiplier,
        4,
    )


def deterioration_at(
    starting_severity: float,
    rate_per_min: float,
    elapsed_minutes: float,
) -> float:
    """Calculate live D(t) = min(100, S0 + rate × elapsed minutes)."""
    start = max(0.0, min(100.0, float(starting_severity)))
    rate = max(0.0, float(rate_per_min))
    elapsed = max(0.0, float(elapsed_minutes))
    return round(min(100.0, start + rate * elapsed), 2)


def severity_category(severity: float) -> int:
    """Map a 0–100 severity to the project's Category 1–4 thresholds."""
    value = max(0.0, min(100.0, float(severity)))
    if value >= 75.0:
        return 1
    if value >= 50.0:
        return 2
    if value >= 25.0:
        return 3
    return 4
