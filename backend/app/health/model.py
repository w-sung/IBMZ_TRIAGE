"""Train and query the Chunk 3 HistGradientBoostingRegressor."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any

from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

from .patients import load_condition_records, load_patient_records, make_synthetic_training_patients
from .scoring import FEATURE_NAMES, model_features, score_patient


@dataclass(frozen=True)
class TrainingReport:
    training_samples: int
    validation_mae: float
    validation_r2: float
    fit_seconds: float
    seed: int


class SeverityPredictor:
    """Small interface for Chunk 4: `predict(patient) -> float` in [0, 100]."""

    def __init__(
        self,
        estimator: HistGradientBoostingRegressor,
        conditions: Mapping[str, Mapping[str, Any]],
    ):
        self._estimator = estimator
        self._conditions = dict(conditions)

    @property
    def estimator(self) -> HistGradientBoostingRegressor:
        """Expose estimator for diagnostics/tests without persisting it to disk."""
        return self._estimator

    def predict(self, patient: Mapping[str, Any]) -> float:
        features = model_features(patient, self._conditions)
        prediction = float(self._estimator.predict([features])[0])
        return round(max(0.0, min(100.0, prediction)), 2)


def _new_estimator(seed: int) -> HistGradientBoostingRegressor:
    # scikit-learn's positive monotonic constraints encode that each feature is
    # already a risk signal: larger values must not reduce predicted severity.
    # This specifically stabilizes SpO2 and hypotension behaviour for the demo.
    return HistGradientBoostingRegressor(
        loss="squared_error",
        learning_rate=0.08,
        max_iter=120,
        max_leaf_nodes=15,
        min_samples_leaf=12,
        l2_regularization=1.0,
        early_stopping=False,
        monotonic_cst=[1] * len(FEATURE_NAMES),
        random_state=seed,
    )


def train_severity_model(
    patient_pool: Sequence[Mapping[str, Any]],
    conditions: Mapping[str, Mapping[str, Any]],
    *,
    seed: int = 42,
    n_samples: int = 5000,
) -> tuple[SeverityPredictor, TrainingReport]:
    """Generate training examples, validate a model, then fit the final model.

    Targets are the deterministic synthetic rule in scoring.py plus seeded
    low-amplitude noise. Metrics describe agreement with that rule, not clinical
    predictive accuracy or real-world outcomes.
    """
    started = time.perf_counter()
    samples = make_synthetic_training_patients(patient_pool, conditions, n_samples, seed)
    features = [model_features(patient, conditions) for patient in samples]
    noise_rng = random.Random(seed + 1)
    labels = [
        max(0.0, min(100.0, score_patient(patient, conditions) + noise_rng.gauss(0.0, 1.25)))
        for patient in samples
    ]

    x_train, x_val, y_train, y_val = train_test_split(
        features,
        labels,
        test_size=0.2,
        random_state=seed,
    )
    validation_estimator = _new_estimator(seed)
    validation_estimator.fit(x_train, y_train)
    val_predictions = validation_estimator.predict(x_val)
    validation_mae = float(mean_absolute_error(y_val, val_predictions))
    validation_r2 = float(r2_score(y_val, val_predictions))

    final_estimator = _new_estimator(seed)
    final_estimator.fit(features, labels)
    elapsed = time.perf_counter() - started
    predictor = SeverityPredictor(final_estimator, conditions)
    report = TrainingReport(
        training_samples=len(samples),
        validation_mae=round(validation_mae, 3),
        validation_r2=round(validation_r2, 3),
        fit_seconds=round(elapsed, 3),
        seed=seed,
    )
    return predictor, report


def _project_root() -> Path:
    # model.py -> health -> app -> backend -> repository root
    return Path(__file__).resolve().parents[3]


@lru_cache(maxsize=4)
def get_default_model(seed: int = 42, n_samples: int = 5000) -> SeverityPredictor:
    """Load project JSON and train once per process (no pickle/joblib artifact).

    Chunk 4 can call `get_default_model().predict(patient)`. The first call does
    the training locally; later calls reuse the in-memory estimator. The cache is
    keyed only by primitive arguments, making it safe for lru_cache.
    """
    root = _project_root()
    patients = load_patient_records(root / "data" / "patients.json")
    conditions = load_condition_records(root / "data" / "conditions.json")
    predictor, _ = train_severity_model(patients, conditions, seed=seed, n_samples=n_samples)
    return predictor
