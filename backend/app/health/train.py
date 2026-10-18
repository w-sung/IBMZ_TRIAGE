"""Train the synthetic TRIAGE health model and print reproducible diagnostics.

Run from the repository root:
    python -m backend.app.health.train

No model binary is written. On LinuxONE the package should come from Ubuntu's
python3-sklearn system package as described in CONTEXT.md.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import fmean

from .model import train_severity_model
from .patients import load_condition_records, load_patient_records
from .scoring import CONDITION_EXPECTED_BANDS, CONDITION_PRIORS


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def main() -> int:
    root = _project_root()
    parser = argparse.ArgumentParser(
        description="Train TRIAGE's synthetic severity model"
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--count", type=int, default=5000, help="synthetic training rows (minimum 40)"
    )
    parser.add_argument("--patients", type=Path, default=root / "data" / "patients.json")
    parser.add_argument("--conditions", type=Path, default=root / "data" / "conditions.json")
    args = parser.parse_args()

    patients = load_patient_records(args.patients)
    conditions = load_condition_records(args.conditions)
    predictor, report = train_severity_model(
        patients, conditions, seed=args.seed, n_samples=args.count
    )

    neutral_vitals = {
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
    neutral_diagnostics: dict[str, float] = {}
    observed_by_condition: dict[str, list[float]] = {}
    for patient in patients:
        condition_id = str(patient.get("condition_id", "unknown"))
        observed_by_condition.setdefault(condition_id, []).append(predictor.predict(patient))
    condition_mean_diagnostics: dict[str, dict[str, object]] = {}
    for condition_id in conditions:
        neutral_patient = {
            "age": 45,
            "sex": "U",
            "condition_id": condition_id,
            "vitals": neutral_vitals,
        }
        neutral_diagnostics[condition_id] = predictor.predict(neutral_patient)
        observed_predictions = observed_by_condition.get(condition_id, [])
        low_high = CONDITION_EXPECTED_BANDS.get(condition_id)
        mean_score = round(fmean(observed_predictions), 2) if observed_predictions else None
        condition_mean_diagnostics[condition_id] = {
            "source_patient_count": len(observed_predictions),
            "source_patient_mean_prediction": mean_score,
            "expected_s0_band_diagnostic_only": list(low_high) if low_high else None,
            "within_expected_s0_band": (
                bool(
                    low_high
                    and mean_score is not None
                    and low_high[0] <= mean_score <= low_high[1]
                )
                if low_high
                else None
            ),
        }

    output = {
        "model": "HistGradientBoostingRegressor",
        "target": "synthetic NEWS2-inspired label + seeded noise (not clinical outcomes)",
        "seed": report.seed,
        "training_samples": report.training_samples,
        "validation_mae": report.validation_mae,
        "validation_r2": report.validation_r2,
        "fit_seconds": report.fit_seconds,
        "condition_neutral_vitals_predictions": neutral_diagnostics,
        "source_patient_condition_mean_diagnostics": condition_mean_diagnostics,
        "condition_priors_without_explicit_metadata": CONDITION_PRIORS,
        "model_persisted": False,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
