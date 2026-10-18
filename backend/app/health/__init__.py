"""TRIAGE synthetic-patient severity prediction and deterioration utilities."""

from .deterioration import calculate_deterioration_rate, deterioration_at, severity_category
from .model import SeverityPredictor, get_default_model, train_severity_model
from .scoring import score_patient

__all__ = [
    "SeverityPredictor",
    "calculate_deterioration_rate",
    "deterioration_at",
    "get_default_model",
    "score_patient",
    "severity_category",
    "train_severity_model",
]
