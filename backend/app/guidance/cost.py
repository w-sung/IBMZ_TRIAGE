"""
TRIAGE — Clinical & Logistical Cost Calculation Logic (Chunk 4)

Implements CONTEXT.md Section 6.5:
  Calculates the cost of routing a specific patient `p` to hospital `h` as the
  `k`-th arrival slot (where k = 0 is the first arrival, k = 1 is the second, etc.).

  Total delay (minutes) =
      drive_minutes
    + hospital.base_wait_min
    + (k * hospital.service_min)
    + corridor_penalty (30 min if k >= hospital.beds_free)
    + specialty_penalty (45 min if hospital lacks patient.needs_specialty)
    + theatre_penalty (20 min if patient.needs_theatre and not hospital.theatre_ready)

  Returned Cost =
      min(100.0, patient.severity_s0 + (patient.deterioration_rate_per_min * total_delay))
      + (0.01 * total_delay)
"""

from __future__ import annotations

from backend.app.sim.entities import Hospital, Patient

# Penalty constants (in equivalent delay minutes) from CONTEXT.md Section 6.5
CORRIDOR_PENALTY_MIN: float = 30.0
MISSING_SPECIALTY_PENALTY_MIN: float = 45.0
THEATRE_NOT_READY_PENALTY_MIN: float = 20.0
TIE_BREAKER_WEIGHT: float = 0.01


def calculate_total_delay(
    patient: Patient,
    hospital: Hospital,
    k: int,
    drive_minutes: float,
) -> float:
    """
    Calculate the total effective delay (in minutes) before definitive treatment starts
    when `patient` is assigned to `hospital` in queue slot `k` (k >= 0).
    """
    slot_idx = max(0, int(k))
    safe_drive_min = max(0.0, float(drive_minutes))

    # 1. Base travel time + hospital baseline ED handover wait + queue slot wait
    total_delay = (
        safe_drive_min
        + float(hospital.base_wait_min)
        + (slot_idx * float(hospital.service_min))
    )

    # 2. Corridor care overflow penalty: triggered if slot k is at or beyond free beds
    free_beds = max(0, int(hospital.beds_total) - int(hospital.beds_occupied))
    if slot_idx >= free_beds:
        total_delay += CORRIDOR_PENALTY_MIN

    # 3. Missing clinical specialty penalty (models delay of secondary inter-hospital transfer)
    needed_spec = (
        patient.needs_specialty.strip().lower()
        if patient.needs_specialty
        else None
    )
    if needed_spec and needed_spec not in ("none", ""):
        if needed_spec not in hospital.specialties:
            total_delay += MISSING_SPECIALTY_PENALTY_MIN

    # 4. Operating theatre readiness penalty
    if patient.needs_theatre and not hospital.theatre_ready:
        total_delay += THEATRE_NOT_READY_PENALTY_MIN

    return total_delay


def calculate_cost(
    patient: Patient,
    hospital: Hospital,
    k: int,
    drive_minutes: float,
) -> float:
    """
    Compute the objective cost of assigning `patient` to `hospital` at arrival slot `k`.

    Formula (CONTEXT.md Section 6.5):
      total_delay = drive_minutes + base_wait_min + (k * service_min)
                    + corridor_penalty + specialty_penalty + theatre_penalty
      cost = min(100, S0 + rate * total_delay) + (0.01 * total_delay)

    Note: The 0.01 * total_delay tie-breaker ensures that even if two hospitals both
    cap out at severity 100 (or have 0.0 deterioration rate for minor injuries),
    the solver strictly prefers the hospital with the shorter total delay.
    """
    total_delay = calculate_total_delay(
        patient=patient,
        hospital=hospital,
        k=k,
        drive_minutes=drive_minutes,
    )

    expected_severity_at_treatment = min(
        100.0,
        float(patient.severity_s0)
        + (float(patient.deterioration_rate_per_min) * total_delay),
    )

    cost = expected_severity_at_treatment + (TIE_BREAKER_WEIGHT * total_delay)
    return float(cost)