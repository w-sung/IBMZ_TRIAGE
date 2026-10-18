"""
TRIAGE — Synthetic Conditions & Patient Generator (Chunk 1)
Generates:
  1. data/conditions.json — The 20 emergency clinical conditions from CONTEXT.md
     with specialty requirements, operating theatre flags, expected S0 severity bands,
     deterioration rates (points/min), and realistic vital-sign generation profiles.
  2. data/patients.json — Deterministically seeded synthetic patient records with
     plausible ages, sex, clinical condition, and full vital signs anchored to
     published NEWS2 / clinical reference ranges.

Uses 100% Python standard library for zero-dependency execution on Windows & s390x.
"""

import argparse
import json
from pathlib import Path
import random
from typing import Any, Dict, List, Tuple


# Resolve project root and output directory
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
CONDITIONS_FILE = DATA_DIR / "conditions.json"
PATIENTS_FILE = DATA_DIR / "patients.json"


# Complete definition of the 20 conditions from CONTEXT.md Section 5.3
# Note: Parameters are illustrative for emergency simulation, not clinical evidence.
CONDITIONS_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "cardiac_arrest",
        "name": "Cardiac arrest",
        "specialty": "cardiac",
        "theatre_needed": False,
        "expected_s0_band": [85, 100],
        "base_rate_per_min": [3.0, 5.0],
        "age_profile": {"mean": 68, "std": 14, "min": 25, "max": 95},
        "female_prob": 0.42,
        "vitals_profile": {
            "hr": {"mean": 35, "std": 30, "min": 0, "max": 180},
            "sbp": {"mean": 45, "std": 20, "min": 0, "max": 90},
            "rr": {"mean": 4, "std": 4, "min": 0, "max": 16},
            "spo2": {"mean": 72, "std": 10, "min": 50, "max": 90},
            "etco2": {"mean": 14, "std": 6, "min": 5, "max": 28},
            "spco": {"mean": 1.5, "std": 0.8, "min": 0.2, "max": 5.0},
            "methb": {"mean": 0.8, "std": 0.4, "min": 0.1, "max": 2.0},
        },
        "ecg_probs": {"vf": 0.45, "vt": 0.20, "asystole": 0.30, "brady": 0.05},
        "st_elevation_prob": 0.35,
        "consciousness_probs": {"unresponsive": 0.92, "pain": 0.08},
    },
    {
        "id": "stemi",
        "name": "Heart attack (STEMI)",
        "specialty": "cardiac",
        "theatre_needed": False,
        "expected_s0_band": [60, 85],
        "base_rate_per_min": [0.8, 1.5],
        "age_profile": {"mean": 66, "std": 12, "min": 35, "max": 92},
        "female_prob": 0.40,
        "vitals_profile": {
            "hr": {"mean": 112, "std": 18, "min": 52, "max": 165},
            "sbp": {"mean": 92, "std": 18, "min": 65, "max": 155},
            "rr": {"mean": 23, "std": 4, "min": 14, "max": 34},
            "spo2": {"mean": 91, "std": 3, "min": 82, "max": 98},
            "etco2": {"mean": 31, "std": 4, "min": 20, "max": 42},
            "spco": {"mean": 1.8, "std": 0.9, "min": 0.3, "max": 5.5},
            "methb": {"mean": 0.7, "std": 0.3, "min": 0.1, "max": 1.8},
        },
        "ecg_probs": {"sinus_tach": 0.55, "sinus": 0.20, "af": 0.15, "vt": 0.05, "brady": 0.05},
        "st_elevation_prob": 0.95,
        "consciousness_probs": {"alert": 0.70, "voice": 0.22, "pain": 0.08},
    },
    {
        "id": "major_haemorrhage",
        "name": "Major traumatic bleeding",
        "specialty": "trauma",
        "theatre_needed": True,
        "expected_s0_band": [70, 95],
        "base_rate_per_min": [2.0, 3.5],
        "age_profile": {"mean": 38, "std": 16, "min": 18, "max": 85},
        "female_prob": 0.35,
        "vitals_profile": {
            "hr": {"mean": 134, "std": 16, "min": 95, "max": 175},
            "sbp": {"mean": 74, "std": 14, "min": 45, "max": 105},
            "rr": {"mean": 28, "std": 5, "min": 18, "max": 40},
            "spo2": {"mean": 89, "std": 4, "min": 78, "max": 97},
            "etco2": {"mean": 24, "std": 4, "min": 14, "max": 34},
            "spco": {"mean": 1.2, "std": 0.6, "min": 0.2, "max": 3.5},
            "methb": {"mean": 0.6, "std": 0.3, "min": 0.1, "max": 1.5},
        },
        "ecg_probs": {"sinus_tach": 0.85, "sinus": 0.10, "brady": 0.05},
        "st_elevation_prob": 0.05,
        "consciousness_probs": {"alert": 0.35, "voice": 0.38, "pain": 0.20, "unresponsive": 0.07},
    },
    {
        "id": "severe_head_injury",
        "name": "Severe head injury",
        "specialty": "trauma",
        "theatre_needed": True,
        "expected_s0_band": [65, 90],
        "base_rate_per_min": [1.0, 2.0],
        "age_profile": {"mean": 42, "std": 19, "min": 18, "max": 88},
        "female_prob": 0.38,
        "vitals_profile": {
            "hr": {"mean": 62, "std": 18, "min": 40, "max": 125},
            "sbp": {"mean": 158, "std": 22, "min": 95, "max": 210},
            "rr": {"mean": 11, "std": 4, "min": 6, "max": 24},
            "spo2": {"mean": 88, "std": 5, "min": 75, "max": 97},
            "etco2": {"mean": 46, "std": 6, "min": 32, "max": 62},
            "spco": {"mean": 1.1, "std": 0.5, "min": 0.2, "max": 3.0},
            "methb": {"mean": 0.6, "std": 0.3, "min": 0.1, "max": 1.5},
        },
        "ecg_probs": {"brady": 0.45, "sinus": 0.35, "sinus_tach": 0.20},
        "st_elevation_prob": 0.02,
        "consciousness_probs": {"unresponsive": 0.35, "pain": 0.40, "voice": 0.20, "alert": 0.05},
    },
    {
        "id": "stroke",
        "name": "Acute stroke",
        "specialty": "stroke",
        "theatre_needed": False,
        "expected_s0_band": [50, 80],
        "base_rate_per_min": [0.8, 1.5],
        "age_profile": {"mean": 72, "std": 12, "min": 40, "max": 95},
        "female_prob": 0.52,
        "vitals_profile": {
            "hr": {"mean": 88, "std": 18, "min": 55, "max": 135},
            "sbp": {"mean": 165, "std": 24, "min": 110, "max": 220},
            "rr": {"mean": 18, "std": 4, "min": 10, "max": 28},
            "spo2": {"mean": 93, "std": 3, "min": 85, "max": 99},
            "etco2": {"mean": 38, "std": 4, "min": 28, "max": 48},
            "spco": {"mean": 1.3, "std": 0.6, "min": 0.2, "max": 3.5},
            "methb": {"mean": 0.7, "std": 0.3, "min": 0.1, "max": 1.6},
        },
        "ecg_probs": {"af": 0.45, "sinus": 0.40, "sinus_tach": 0.10, "brady": 0.05},
        "st_elevation_prob": 0.04,
        "consciousness_probs": {"voice": 0.42, "alert": 0.35, "pain": 0.18, "unresponsive": 0.05},
    },
    {
        "id": "resp_failure",
        "name": "Severe asthma or respiratory failure",
        "specialty": "general",
        "theatre_needed": False,
        "expected_s0_band": [55, 85],
        "base_rate_per_min": [1.2, 2.2],
        "age_profile": {"mean": 54, "std": 20, "min": 18, "max": 90},
        "female_prob": 0.54,
        "vitals_profile": {
            "hr": {"mean": 124, "std": 16, "min": 85, "max": 160},
            "sbp": {"mean": 118, "std": 18, "min": 80, "max": 160},
            "rr": {"mean": 32, "std": 5, "min": 22, "max": 46},
            "spo2": {"mean": 84, "std": 5, "min": 70, "max": 92},
            "etco2": {"mean": 54, "std": 8, "min": 38, "max": 75},
            "spco": {"mean": 1.6, "std": 0.8, "min": 0.2, "max": 4.5},
            "methb": {"mean": 0.7, "std": 0.3, "min": 0.1, "max": 1.6},
        },
        "ecg_probs": {"sinus_tach": 0.80, "sinus": 0.12, "af": 0.08},
        "st_elevation_prob": 0.02,
        "consciousness_probs": {"alert": 0.50, "voice": 0.35, "pain": 0.12, "unresponsive": 0.03},
    },
    {
        "id": "anaphylaxis",
        "name": "Anaphylaxis",
        "specialty": "general",
        "theatre_needed": False,
        "expected_s0_band": [60, 85],
        "base_rate_per_min": [2.0, 3.0],
        "age_profile": {"mean": 34, "std": 15, "min": 18, "max": 75},
        "female_prob": 0.55,
        "vitals_profile": {
            "hr": {"mean": 130, "std": 15, "min": 95, "max": 170},
            "sbp": {"mean": 78, "std": 14, "min": 50, "max": 110},
            "rr": {"mean": 29, "std": 5, "min": 20, "max": 42},
            "spo2": {"mean": 87, "std": 4, "min": 75, "max": 95},
            "etco2": {"mean": 30, "std": 5, "min": 18, "max": 45},
            "spco": {"mean": 1.0, "std": 0.5, "min": 0.1, "max": 2.5},
            "methb": {"mean": 0.6, "std": 0.3, "min": 0.1, "max": 1.4},
        },
        "ecg_probs": {"sinus_tach": 0.88, "sinus": 0.12},
        "st_elevation_prob": 0.01,
        "consciousness_probs": {"alert": 0.48, "voice": 0.36, "pain": 0.12, "unresponsive": 0.04},
    },
    {
        "id": "septic_shock",
        "name": "Septic shock",
        "specialty": "general",
        "theatre_needed": False,
        "expected_s0_band": [55, 80],
        "base_rate_per_min": [0.6, 1.0],
        "age_profile": {"mean": 70, "std": 14, "min": 30, "max": 94},
        "female_prob": 0.48,
        "vitals_profile": {
            "hr": {"mean": 122, "std": 16, "min": 90, "max": 160},
            "sbp": {"mean": 80, "std": 12, "min": 55, "max": 105},
            "rr": {"mean": 26, "std": 4, "min": 18, "max": 38},
            "spo2": {"mean": 90, "std": 4, "min": 80, "max": 97},
            "etco2": {"mean": 26, "std": 4, "min": 16, "max": 35},
            "spco": {"mean": 1.3, "std": 0.6, "min": 0.2, "max": 3.0},
            "methb": {"mean": 0.9, "std": 0.4, "min": 0.1, "max": 2.2},
        },
        "ecg_probs": {"sinus_tach": 0.75, "af": 0.18, "sinus": 0.07},
        "st_elevation_prob": 0.03,
        "consciousness_probs": {"voice": 0.45, "alert": 0.35, "pain": 0.16, "unresponsive": 0.04},
    },
    {
        "id": "ruptured_aaa",
        "name": "Ruptured aortic aneurysm",
        "specialty": "vascular",
        "theatre_needed": True,
        "expected_s0_band": [75, 95],
        "base_rate_per_min": [2.0, 3.0],
        "age_profile": {"mean": 74, "std": 8, "min": 55, "max": 92},
        "female_prob": 0.25,
        "vitals_profile": {
            "hr": {"mean": 128, "std": 18, "min": 85, "max": 170},
            "sbp": {"mean": 68, "std": 15, "min": 40, "max": 98},
            "rr": {"mean": 26, "std": 5, "min": 16, "max": 38},
            "spo2": {"mean": 88, "std": 4, "min": 76, "max": 96},
            "etco2": {"mean": 22, "std": 5, "min": 12, "max": 32},
            "spco": {"mean": 1.7, "std": 0.8, "min": 0.3, "max": 4.5},
            "methb": {"mean": 0.8, "std": 0.3, "min": 0.1, "max": 1.8},
        },
        "ecg_probs": {"sinus_tach": 0.72, "af": 0.15, "brady": 0.08, "vt": 0.05},
        "st_elevation_prob": 0.10,
        "consciousness_probs": {"voice": 0.40, "pain": 0.32, "alert": 0.20, "unresponsive": 0.08},
    },
    {
        "id": "chest_trauma",
        "name": "Chest trauma / tension pneumothorax",
        "specialty": "trauma",
        "theatre_needed": False,
        "expected_s0_band": [60, 85],
        "base_rate_per_min": [1.5, 2.5],
        "age_profile": {"mean": 41, "std": 17, "min": 18, "max": 82},
        "female_prob": 0.32,
        "vitals_profile": {
            "hr": {"mean": 126, "std": 16, "min": 90, "max": 165},
            "sbp": {"mean": 84, "std": 15, "min": 55, "max": 120},
            "rr": {"mean": 31, "std": 5, "min": 20, "max": 44},
            "spo2": {"mean": 85, "std": 5, "min": 72, "max": 94},
            "etco2": {"mean": 29, "std": 6, "min": 18, "max": 44},
            "spco": {"mean": 1.2, "std": 0.6, "min": 0.2, "max": 3.2},
            "methb": {"mean": 0.6, "std": 0.3, "min": 0.1, "max": 1.5},
        },
        "ecg_probs": {"sinus_tach": 0.85, "sinus": 0.15},
        "st_elevation_prob": 0.03,
        "consciousness_probs": {"alert": 0.52, "voice": 0.32, "pain": 0.12, "unresponsive": 0.04},
    },
    {
        "id": "co_poisoning",
        "name": "Carbon monoxide poisoning",
        "specialty": "general",
        "theatre_needed": False,
        "expected_s0_band": [40, 75],
        "base_rate_per_min": [0.5, 1.0],
        "age_profile": {"mean": 46, "std": 18, "min": 18, "max": 85},
        "female_prob": 0.50,
        "vitals_profile": {
            "hr": {"mean": 110, "std": 15, "min": 75, "max": 145},
            "sbp": {"mean": 108, "std": 16, "min": 75, "max": 145},
            "rr": {"mean": 24, "std": 4, "min": 14, "max": 34},
            # Standard pulse oximetry over-reads in CO poisoning, hence high SpO2 + elevated SpCO
            "spo2": {"mean": 96, "std": 2, "min": 90, "max": 100},
            "etco2": {"mean": 33, "std": 4, "min": 24, "max": 42},
            "spco": {"mean": 24.5, "std": 6.0, "min": 15.0, "max": 40.0},
            "methb": {"mean": 1.4, "std": 0.6, "min": 0.3, "max": 3.5},
        },
        "ecg_probs": {"sinus_tach": 0.68, "sinus": 0.27, "af": 0.05},
        "st_elevation_prob": 0.06,
        "consciousness_probs": {"voice": 0.45, "alert": 0.35, "pain": 0.15, "unresponsive": 0.05},
    },
    {
        "id": "opioid_overdose",
        "name": "Opioid overdose",
        "specialty": "general",
        "theatre_needed": False,
        "expected_s0_band": [45, 80],
        "base_rate_per_min": [1.0, 2.0],
        "age_profile": {"mean": 36, "std": 12, "min": 18, "max": 70},
        "female_prob": 0.38,
        "vitals_profile": {
            "hr": {"mean": 56, "std": 12, "min": 38, "max": 90},
            "sbp": {"mean": 92, "std": 14, "min": 60, "max": 125},
            "rr": {"mean": 6, "std": 2, "min": 3, "max": 12},
            "spo2": {"mean": 82, "std": 6, "min": 65, "max": 93},
            "etco2": {"mean": 58, "std": 8, "min": 44, "max": 78},
            "spco": {"mean": 2.1, "std": 1.0, "min": 0.3, "max": 5.5},
            "methb": {"mean": 0.8, "std": 0.4, "min": 0.1, "max": 2.0},
        },
        "ecg_probs": {"brady": 0.55, "sinus": 0.40, "sinus_tach": 0.05},
        "st_elevation_prob": 0.01,
        "consciousness_probs": {"unresponsive": 0.45, "pain": 0.38, "voice": 0.15, "alert": 0.02},
    },
    {
        "id": "diabetic_emergency",
        "name": "DKA / severe hypoglycaemia",
        "specialty": "general",
        "theatre_needed": False,
        "expected_s0_band": [35, 65],
        "base_rate_per_min": [0.3, 0.7],
        "age_profile": {"mean": 48, "std": 20, "min": 18, "max": 85},
        "female_prob": 0.50,
        "vitals_profile": {
            "hr": {"mean": 108, "std": 14, "min": 75, "max": 140},
            "sbp": {"mean": 102, "std": 16, "min": 72, "max": 140},
            "rr": {"mean": 24, "std": 4, "min": 14, "max": 34},
            "spo2": {"mean": 95, "std": 2, "min": 90, "max": 99},
            "etco2": {"mean": 24, "std": 5, "min": 14, "max": 36},
            "spco": {"mean": 1.1, "std": 0.5, "min": 0.2, "max": 2.8},
            "methb": {"mean": 0.7, "std": 0.3, "min": 0.1, "max": 1.5},
        },
        "ecg_probs": {"sinus_tach": 0.60, "sinus": 0.35, "af": 0.05},
        "st_elevation_prob": 0.02,
        "consciousness_probs": {"voice": 0.46, "alert": 0.36, "pain": 0.15, "unresponsive": 0.03},
    },
    {
        "id": "severe_burns",
        "name": "Severe burns",
        "specialty": "burns",
        "theatre_needed": False,
        "expected_s0_band": [55, 85],
        "base_rate_per_min": [0.8, 1.5],
        "age_profile": {"mean": 40, "std": 18, "min": 18, "max": 82},
        "female_prob": 0.42,
        "vitals_profile": {
            "hr": {"mean": 126, "std": 16, "min": 92, "max": 165},
            "sbp": {"mean": 94, "std": 16, "min": 65, "max": 135},
            "rr": {"mean": 26, "std": 5, "min": 16, "max": 38},
            "spo2": {"mean": 90, "std": 4, "min": 80, "max": 98},
            "etco2": {"mean": 31, "std": 5, "min": 20, "max": 44},
            "spco": {"mean": 12.0, "std": 5.5, "min": 2.0, "max": 28.0},
            "methb": {"mean": 1.8, "std": 0.8, "min": 0.4, "max": 4.5},
        },
        "ecg_probs": {"sinus_tach": 0.82, "sinus": 0.18},
        "st_elevation_prob": 0.02,
        "consciousness_probs": {"alert": 0.55, "voice": 0.30, "pain": 0.12, "unresponsive": 0.03},
    },
    {
        "id": "obstetric_haemorrhage",
        "name": "Obstetric haemorrhage",
        "specialty": "obstetric",
        "theatre_needed": True,
        "expected_s0_band": [65, 90],
        "base_rate_per_min": [1.5, 2.5],
        "age_profile": {"mean": 31, "std": 6, "min": 19, "max": 45},
        "female_prob": 1.0,
        "vitals_profile": {
            "hr": {"mean": 132, "std": 15, "min": 98, "max": 170},
            "sbp": {"mean": 76, "std": 13, "min": 50, "max": 105},
            "rr": {"mean": 27, "std": 4, "min": 18, "max": 38},
            "spo2": {"mean": 91, "std": 3, "min": 82, "max": 98},
            "etco2": {"mean": 25, "std": 4, "min": 16, "max": 34},
            "spco": {"mean": 0.9, "std": 0.4, "min": 0.1, "max": 2.2},
            "methb": {"mean": 0.6, "std": 0.3, "min": 0.1, "max": 1.4},
        },
        "ecg_probs": {"sinus_tach": 0.90, "sinus": 0.10},
        "st_elevation_prob": 0.01,
        "consciousness_probs": {"alert": 0.45, "voice": 0.38, "pain": 0.14, "unresponsive": 0.03},
    },
    {
        "id": "pulmonary_embolism",
        "name": "Pulmonary embolism",
        "specialty": "general",
        "theatre_needed": False,
        "expected_s0_band": [55, 80],
        "base_rate_per_min": [0.8, 1.4],
        "age_profile": {"mean": 61, "std": 16, "min": 25, "max": 90},
        "female_prob": 0.54,
        "vitals_profile": {
            "hr": {"mean": 118, "std": 15, "min": 88, "max": 155},
            "sbp": {"mean": 94, "std": 16, "min": 65, "max": 130},
            "rr": {"mean": 27, "std": 4, "min": 18, "max": 38},
            "spo2": {"mean": 87, "std": 4, "min": 76, "max": 94},
            "etco2": {"mean": 25, "std": 4, "min": 16, "max": 34},
            "spco": {"mean": 1.3, "std": 0.6, "min": 0.2, "max": 3.2},
            "methb": {"mean": 0.7, "std": 0.3, "min": 0.1, "max": 1.6},
        },
        "ecg_probs": {"sinus_tach": 0.75, "af": 0.15, "sinus": 0.10},
        "st_elevation_prob": 0.05,
        "consciousness_probs": {"alert": 0.62, "voice": 0.28, "pain": 0.08, "unresponsive": 0.02},
    },
    {
        "id": "status_epilepticus",
        "name": "Prolonged seizure",
        "specialty": "general",
        "theatre_needed": False,
        "expected_s0_band": [45, 75],
        "base_rate_per_min": [0.8, 1.5],
        "age_profile": {"mean": 44, "std": 20, "min": 18, "max": 85},
        "female_prob": 0.48,
        "vitals_profile": {
            "hr": {"mean": 120, "std": 16, "min": 85, "max": 158},
            "sbp": {"mean": 136, "std": 20, "min": 95, "max": 180},
            "rr": {"mean": 24, "std": 5, "min": 12, "max": 36},
            "spo2": {"mean": 89, "std": 4, "min": 78, "max": 96},
            "etco2": {"mean": 47, "std": 7, "min": 32, "max": 64},
            "spco": {"mean": 1.2, "std": 0.5, "min": 0.2, "max": 3.0},
            "methb": {"mean": 0.7, "std": 0.3, "min": 0.1, "max": 1.6},
        },
        "ecg_probs": {"sinus_tach": 0.78, "sinus": 0.22},
        "st_elevation_prob": 0.01,
        "consciousness_probs": {"unresponsive": 0.40, "pain": 0.38, "voice": 0.20, "alert": 0.02},
    },
    {
        "id": "gi_bleed",
        "name": "Upper GI bleed",
        "specialty": "general",
        "theatre_needed": False,
        "expected_s0_band": [45, 75],
        "base_rate_per_min": [0.7, 1.4],
        "age_profile": {"mean": 64, "std": 15, "min": 28, "max": 92},
        "female_prob": 0.42,
        "vitals_profile": {
            "hr": {"mean": 114, "std": 15, "min": 82, "max": 150},
            "sbp": {"mean": 88, "std": 14, "min": 60, "max": 122},
            "rr": {"mean": 22, "std": 4, "min": 14, "max": 32},
            "spo2": {"mean": 93, "std": 3, "min": 86, "max": 99},
            "etco2": {"mean": 29, "std": 4, "min": 20, "max": 38},
            "spco": {"mean": 1.4, "std": 0.7, "min": 0.2, "max": 3.8},
            "methb": {"mean": 0.7, "std": 0.3, "min": 0.1, "max": 1.6},
        },
        "ecg_probs": {"sinus_tach": 0.70, "sinus": 0.22, "af": 0.08},
        "st_elevation_prob": 0.02,
        "consciousness_probs": {"alert": 0.60, "voice": 0.30, "pain": 0.08, "unresponsive": 0.02},
    },
    {
        "id": "long_bone_fracture",
        "name": "Fractured femur / long bone",
        "specialty": "trauma",
        "theatre_needed": True,
        "expected_s0_band": [25, 45],
        "base_rate_per_min": [0.15, 0.3],
        "age_profile": {"mean": 52, "std": 22, "min": 18, "max": 92},
        "female_prob": 0.50,
        "vitals_profile": {
            "hr": {"mean": 96, "std": 12, "min": 68, "max": 125},
            "sbp": {"mean": 118, "std": 15, "min": 90, "max": 155},
            "rr": {"mean": 19, "std": 3, "min": 12, "max": 26},
            "spo2": {"mean": 96, "std": 2, "min": 92, "max": 100},
            "etco2": {"mean": 37, "std": 3, "min": 30, "max": 44},
            "spco": {"mean": 1.1, "std": 0.5, "min": 0.2, "max": 2.5},
            "methb": {"mean": 0.6, "std": 0.2, "min": 0.1, "max": 1.3},
        },
        "ecg_probs": {"sinus": 0.65, "sinus_tach": 0.32, "af": 0.03},
        "st_elevation_prob": 0.0,
        "consciousness_probs": {"alert": 0.92, "voice": 0.08},
    },
    {
        "id": "minor_injury",
        "name": "Dislocated toe, sprain, small cut",
        "specialty": "none",
        "theatre_needed": False,
        "expected_s0_band": [5, 20],
        "base_rate_per_min": [0.0, 0.05],
        "age_profile": {"mean": 36, "std": 16, "min": 18, "max": 80},
        "female_prob": 0.49,
        "vitals_profile": {
            "hr": {"mean": 78, "std": 10, "min": 58, "max": 100},
            "sbp": {"mean": 124, "std": 12, "min": 102, "max": 148},
            "rr": {"mean": 15, "std": 2, "min": 12, "max": 20},
            "spo2": {"mean": 98, "std": 1, "min": 95, "max": 100},
            "etco2": {"mean": 39, "std": 2, "min": 35, "max": 44},
            "spco": {"mean": 0.9, "std": 0.4, "min": 0.1, "max": 2.0},
            "methb": {"mean": 0.5, "std": 0.2, "min": 0.1, "max": 1.1},
        },
        "ecg_probs": {"sinus": 0.96, "sinus_tach": 0.04},
        "st_elevation_prob": 0.0,
        "consciousness_probs": {"alert": 1.0},
    },
]


def clipped_gauss(
    rng: random.Random,
    mean: float,
    std: float,
    low: float,
    high: float,
    as_int: bool = True,
) -> float | int:
    """Sample from a normal distribution and clip to plausible clinical bounds."""
    val = rng.gauss(mean, std)
    clipped = max(low, min(high, val))
    if as_int:
        return int(round(clipped))
    return round(clipped, 1)


def sample_from_prob_map(rng: random.Random, prob_map: Dict[str, float]) -> str:
    """Deterministically sample a categorical key from a dictionary of probabilities."""
    keys = list(prob_map.keys())
    weights = list(prob_map.values())
    return rng.choices(keys, weights=weights, k=1)[0]


def generate_single_patient(
    rng: random.Random,
    patient_index: int,
    condition: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Generate a single synthetic patient record strictly following the
    contract in CONTEXT.md Section 5.3.
    """
    age_prof = condition["age_profile"]
    age = clipped_gauss(
        rng,
        age_prof["mean"],
        age_prof["std"],
        age_prof["min"],
        age_prof["max"],
        as_int=True,
    )

    sex = "F" if rng.random() < condition["female_prob"] else "M"
    vp = condition["vitals_profile"]

    hr = clipped_gauss(rng, vp["hr"]["mean"], vp["hr"]["std"], vp["hr"]["min"], vp["hr"]["max"], as_int=True)
    sbp = clipped_gauss(rng, vp["sbp"]["mean"], vp["sbp"]["std"], vp["sbp"]["min"], vp["sbp"]["max"], as_int=True)
    rr = clipped_gauss(rng, vp["rr"]["mean"], vp["rr"]["std"], vp["rr"]["min"], vp["rr"]["max"], as_int=True)
    spo2 = clipped_gauss(rng, vp["spo2"]["mean"], vp["spo2"]["std"], vp["spo2"]["min"], vp["spo2"]["max"], as_int=True)
    etco2 = clipped_gauss(rng, vp["etco2"]["mean"], vp["etco2"]["std"], vp["etco2"]["min"], vp["etco2"]["max"], as_int=True)
    spco = clipped_gauss(rng, vp["spco"]["mean"], vp["spco"]["std"], vp["spco"]["min"], vp["spco"]["max"], as_int=False)
    methb = clipped_gauss(rng, vp["methb"]["mean"], vp["methb"]["std"], vp["methb"]["min"], vp["methb"]["max"], as_int=False)

    ecg_rhythm = sample_from_prob_map(rng, condition["ecg_probs"])
    if ecg_rhythm == "asystole":
        hr = 0

    st_elevation = rng.random() < condition["st_elevation_prob"]
    consciousness = sample_from_prob_map(rng, condition["consciousness_probs"])

    return {
        "patient_id": f"p_{patient_index:03d}",
        "age": age,
        "sex": sex,
        "condition_id": condition["id"],
        "vitals": {
            "hr": hr,
            "sbp": sbp,
            "rr": rr,
            "spo2": spo2,
            "etco2": etco2,
            "spco": spco,
            "methb": methb,
            "ecg_rhythm": ecg_rhythm,
            "st_elevation": st_elevation,
            "consciousness": consciousness,
        },
    }


def generate_dataset(
    seed: int = 42,
    num_patients: int = 100,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Generate the conditions catalog and a list of synthetic patients.
    Ensures every one of the 20 conditions is represented, then samples
    across the catalog using seeded randomness.
    """
    rng = random.Random(seed)
    patients: List[Dict[str, Any]] = []

    for idx in range(1, num_patients + 1):
        # Guarantee uniform coverage across all 20 conditions first, then random draw
        if idx <= len(CONDITIONS_CATALOG):
            condition = CONDITIONS_CATALOG[idx - 1]
        else:
            condition = rng.choice(CONDITIONS_CATALOG)

        patient = generate_single_patient(rng, idx, condition)
        patients.append(patient)

    return CONDITIONS_CATALOG, patients


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate data/conditions.json and data/patients.json for TRIAGE."
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic random seed (default: 42)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=100,
        help="Number of synthetic patients to generate (default: 100)",
    )
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    conditions, patients = generate_dataset(seed=args.seed, num_patients=args.count)

    with CONDITIONS_FILE.open("w", encoding="utf-8") as f_cond:
        json.dump(conditions, f_cond, indent=2)

    with PATIENTS_FILE.open("w", encoding="utf-8") as f_pat:
        json.dump(patients, f_pat, indent=2)

    print("=" * 68)
    print("TRIAGE — Synthetic Clinical Data Generator Complete!")
    print("=" * 68)
    print(f"Seed used            : {args.seed}")
    print(f"Conditions written   : {len(conditions)} -> {CONDITIONS_FILE}")
    print(f"Patients written     : {len(patients)} -> {PATIENTS_FILE}")
    print("-" * 68)
    print("Sample generated patient records:")
    for sample in patients[:3]:
        v = sample["vitals"]
        print(
            f"  [{sample['patient_id']}] {sample['age']}{sample['sex']} | "
            f"Condition: {sample['condition_id']:<18} | "
            f"HR: {v['hr']:>3} bpm, SBP: {v['sbp']:>3} mmHg, "
            f"SpO2: {v['spo2']:>3}%, Rhythm: {v['ecg_rhythm']}"
        )
    print("=" * 68)


if __name__ == "__main__":
    main()