"""Patient JSON loading and deterministic synthetic training-data augmentation."""

from __future__ import annotations

import json
import random
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .scoring import CONDITION_PRIORS


def load_patient_records(path: str | Path) -> list[dict[str, Any]]:
    """Load patients from a JSON list or {'patients': [...]} object."""
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Patient data file not found: {file_path}")
    raw = json.loads(file_path.read_text(encoding="utf-8"))
    records = raw.get("patients") if isinstance(raw, Mapping) else raw
    if not isinstance(records, list) or not records:
        raise ValueError(f"Expected a non-empty patient list in {file_path}")
    patients = [row for row in records if isinstance(row, dict) and row.get("condition_id")]
    if not patients:
        raise ValueError(f"No valid patient records with condition_id found in {file_path}")
    return patients


def load_condition_records(path: str | Path) -> dict[str, dict[str, Any]]:
    """Normalize conditions JSON as either a list or an ID-keyed mapping."""
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Condition data file not found: {file_path}")
    raw = json.loads(file_path.read_text(encoding="utf-8"))
    if isinstance(raw, Mapping) and isinstance(raw.get("conditions"), list):
        records = raw["conditions"]
    elif isinstance(raw, Mapping) and isinstance(raw.get("conditions"), Mapping):
        records = []
        for key, value in raw["conditions"].items():
            if isinstance(value, Mapping):
                row = dict(value)
                row.setdefault("id", str(key))
                records.append(row)
    elif isinstance(raw, list):
        records = raw
    elif isinstance(raw, Mapping):
        records = []
        for key, value in raw.items():
            if isinstance(value, Mapping):
                row = dict(value)
                row.setdefault("id", str(key))
                records.append(row)
    else:
        records = []

    normalized: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            continue
        condition_id = record.get("id", record.get("condition_id", record.get("slug")))
        if condition_id:
            normalized[str(condition_id)] = dict(record)
    if not normalized:
        raise ValueError(f"No valid condition records with id/condition_id found in {file_path}")
    return normalized


def _clip(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def _vitals_of(patient: Mapping[str, Any]) -> dict[str, Any]:
    raw = patient.get("vitals", {})
    return dict(raw) if isinstance(raw, Mapping) else {}


def _fallback_patient(condition_id: str) -> dict[str, Any]:
    """Create a sensible synthetic seed record if a condition lacks a template."""
    templates: dict[str, dict[str, Any]] = {
        "cardiac_arrest": {
            "hr": 130, "sbp": 70, "rr": 4, "spo2": 78, "etco2": 18,
            "ecg_rhythm": "vf", "consciousness": "unresponsive",
        },
        "stemi": {
            "hr": 115, "sbp": 95, "rr": 22, "spo2": 93, "etco2": 32,
            "ecg_rhythm": "sinus_tach", "st_elevation": True,
        },
        "major_haemorrhage": {
            "hr": 125, "sbp": 82, "rr": 25, "spo2": 92, "etco2": 25,
            "ecg_rhythm": "sinus_tach",
        },
        "severe_head_injury": {
            "hr": 105, "sbp": 100, "rr": 22, "spo2": 93, "consciousness": "voice",
        },
        "stroke": {"hr": 95, "sbp": 160, "rr": 18, "spo2": 95, "consciousness": "confused"},
        "resp_failure": {"hr": 120, "sbp": 115, "rr": 30, "spo2": 86, "etco2": 55},
        "anaphylaxis": {"hr": 130, "sbp": 85, "rr": 28, "spo2": 90, "ecg_rhythm": "sinus_tach"},
        "septic_shock": {"hr": 115, "sbp": 88, "rr": 26, "spo2": 92, "etco2": 28},
        "ruptured_aaa": {"hr": 125, "sbp": 75, "rr": 24, "spo2": 93, "etco2": 24},
        "chest_trauma": {"hr": 120, "sbp": 90, "rr": 28, "spo2": 89, "etco2": 25},
        "co_poisoning": {"hr": 100, "sbp": 120, "rr": 20, "spo2": 98, "spco": 18, "etco2": 35},
        "opioid_overdose": {"hr": 58, "sbp": 105, "rr": 7, "spo2": 84, "etco2": 55, "consciousness": "pain"},
        "diabetic_emergency": {"hr": 100, "sbp": 115, "rr": 22, "spo2": 96, "consciousness": "confused"},
        "severe_burns": {"hr": 115, "sbp": 100, "rr": 24, "spo2": 94},
        "obstetric_haemorrhage": {"hr": 125, "sbp": 85, "rr": 24, "spo2": 93, "etco2": 27},
        "pulmonary_embolism": {"hr": 115, "sbp": 100, "rr": 25, "spo2": 91, "etco2": 28},
        "status_epilepticus": {"hr": 115, "sbp": 120, "rr": 25, "spo2": 91, "consciousness": "pain"},
        "gi_bleed": {"hr": 110, "sbp": 95, "rr": 22, "spo2": 95},
        "long_bone_fracture": {"hr": 95, "sbp": 115, "rr": 18, "spo2": 97},
        "minor_injury": {"hr": 78, "sbp": 120, "rr": 16, "spo2": 98},
    }
    vitals = {
        "hr": 80, "sbp": 120, "rr": 16, "spo2": 97, "etco2": 40,
        "spco": 0.0, "methb": 0.0, "ecg_rhythm": "sinus",
        "st_elevation": False, "consciousness": "alert",
    }
    vitals.update(templates.get(condition_id, {}))
    return {
        "patient_id": f"train_{condition_id}",
        "age": 50,
        "sex": "U",
        "condition_id": condition_id,
        "vitals": vitals,
    }


def _jitter_patient(
    source: Mapping[str, Any],
    condition_id: str,
    rng: random.Random,
    index: int,
) -> dict[str, Any]:
    patient = dict(source)
    patient["patient_id"] = f"synthetic_train_{index:05d}"
    patient["condition_id"] = condition_id
    age = float(source.get("age", 50) or 50)
    patient["age"] = int(round(_clip(rng.gauss(age, 12.0), 18.0, 100.0)))
    vitals = _vitals_of(source)

    def numeric(
        key: str,
        default: float,
        sd: float,
        low: float,
        high: float,
        integral: bool = True,
    ) -> int | float:
        try:
            base = float(vitals.get(key, default))
        except (TypeError, ValueError):
            base = default
        result = _clip(rng.gauss(base, sd), low, high)
        return int(round(result)) if integral else round(result, 2)

    generated_vitals = {
        "hr": numeric("hr", 80, 14, 25, 240),
        "sbp": numeric("sbp", 120, 14, 40, 240),
        "rr": numeric("rr", 16, 4, 4, 60),
        "spo2": numeric("spo2", 97, 2.5, 50, 100),
        "etco2": numeric("etco2", 40, 6, 5, 80),
        "spco": numeric("spco", 0, 1.5, 0, 40, integral=False),
        "methb": numeric("methb", 0, 1.0, 0, 30, integral=False),
        "ecg_rhythm": str(vitals.get("ecg_rhythm", "sinus")),
        "st_elevation": bool(vitals.get("st_elevation", False)),
        "consciousness": str(vitals.get("consciousness", "alert")),
    }
    # Small deterministic variation prevents every clone sharing identical flags.
    if rng.random() < 0.08:
        generated_vitals["st_elevation"] = not generated_vitals["st_elevation"]
    if rng.random() < 0.12:
        generated_vitals["consciousness"] = rng.choice(["alert", "voice", "pain", "unresponsive"])
    if rng.random() < 0.08:
        generated_vitals["ecg_rhythm"] = rng.choice(
            ["sinus", "sinus_tach", "brady", "af", "vt", "vf", "asystole"]
        )
    patient["vitals"] = generated_vitals
    return patient


def make_synthetic_training_patients(
    patient_pool: Sequence[Mapping[str, Any]],
    conditions: Mapping[str, Mapping[str, Any]],
    count: int = 5000,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Create a balanced, repeatable synthetic training set from patient templates.

    No personal or real patient data is expected. The existing patient file is
    itself synthetic; its records are jittered and re-labelled by scoring.py.
    Sampling is stratified by known condition so rare conditions are represented.
    """
    if count < 40:
        raise ValueError("Training count must be at least 40 to cover 20 conditions")
    if not patient_pool:
        raise ValueError("At least one source patient template is required")

    rng = random.Random(seed)
    known_ids = list(conditions.keys()) or list(CONDITION_PRIORS.keys())
    for patient in patient_pool:
        condition_id = str(patient.get("condition_id", ""))
        if condition_id and condition_id not in known_ids:
            known_ids.append(condition_id)
    if not known_ids:
        raise ValueError("No condition IDs found in conditions or patient data")

    by_condition: dict[str, list[Mapping[str, Any]]] = {
        condition_id: [] for condition_id in known_ids
    }
    for patient in patient_pool:
        condition_id = str(patient.get("condition_id", ""))
        if condition_id in by_condition:
            by_condition[condition_id].append(patient)

    generated: list[dict[str, Any]] = []
    for index in range(count):
        condition_id = known_ids[index % len(known_ids)]
        templates = by_condition.get(condition_id) or []
        if templates:
            source = rng.choice(templates)
        else:
            source = _fallback_patient(condition_id)
        generated.append(_jitter_patient(source, condition_id, rng, index))
    rng.shuffle(generated)
    return generated
