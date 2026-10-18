"""
TRIAGE — Routing Policy Comparison Interface (Chunk 4)

Implements CONTEXT.md Section 6.5 Baselines:
  - NEAREST: Naive baseline that sends every ambulance independently to the
    hospital with the lowest drive_minutes, ignoring beds, queues, and specialties.
  - TRIAGE: Intelligent anti-stampede routing that calls `optimize_assignments`
    from `backend.app.guidance.assign` to jointly optimize across all ambulances.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from backend.app.guidance.assign import lookup_drive_minutes, optimize_assignments
from backend.app.sim.entities import Ambulance, Hospital


def assign_nearest(
    ambulances: list[Ambulance],
    hospitals: list[Hospital],
    travel_time_matrix: dict[Any, Any] | np.ndarray,
) -> dict[str, str]:
    """
    NEAREST Baseline Policy:
    Assigns each ambulance independently to the hospital with the absolute
    lowest `drive_minutes`, completely ignoring bed occupancy, inbound queues,
    operating theatre readiness, and clinical specialties.
    """
    if not ambulances:
        return {}
    if not hospitals:
        raise ValueError("Cannot assign ambulances: `hospitals` list is empty.")

    assignments: dict[str, str] = {}

    for amb_idx, amb in enumerate(ambulances):
        best_hosp_id = hospitals[0].id
        best_drive_min = float("inf")

        for hosp_idx, hosp in enumerate(hospitals):
            drive_min = lookup_drive_minutes(
                travel_time_matrix=travel_time_matrix,
                ambulance=amb,
                hospital=hosp,
                amb_idx=amb_idx,
                hosp_idx=hosp_idx,
            )
            if drive_min < best_drive_min:
                best_drive_min = drive_min
                best_hosp_id = hosp.id

        assignments[amb.id] = best_hosp_id

    return assignments


def assign_triage(
    ambulances: list[Ambulance],
    hospitals: list[Hospital],
    travel_time_matrix: dict[Any, Any] | np.ndarray,
    pre_committed_slots: dict[str, int] | None = None,
) -> dict[str, str]:
    """
    TRIAGE AI Policy:
    Jointly assigns all ambulances using the Hungarian Algorithm to minimize
    total expected patient deterioration at the moment hospital treatment begins.
    """
    return optimize_assignments(
        ambulances=ambulances,
        hospitals=hospitals,
        travel_time_matrix=travel_time_matrix,
        pre_committed_slots=pre_committed_slots,
    )


# Convenient policy registry for the simulation engine and evaluation scripts
POLICIES = {
    "NEAREST": assign_nearest,
    "TRIAGE": assign_triage,
}


def apply_policy(
    policy_name: str,
    ambulances: list[Ambulance],
    hospitals: list[Hospital],
    travel_time_matrix: dict[Any, Any] | np.ndarray,
    pre_committed_slots: dict[str, int] | None = None,
) -> dict[str, str]:
    """
    Dispatch helper so the simulator or API can pass either 'NEAREST' or 'TRIAGE'.
    """
    normalized = str(policy_name).strip().upper()
    if normalized == "NEAREST":
        return assign_nearest(ambulances, hospitals, travel_time_matrix)
    if normalized == "TRIAGE":
        return assign_triage(
            ambulances,
            hospitals,
            travel_time_matrix,
            pre_committed_slots=pre_committed_slots,
        )
    raise ValueError(f"Unknown routing policy '{policy_name}'. Expected 'NEAREST' or 'TRIAGE'.")


if __name__ == "__main__":
    # Quick side-by-side demonstration of NEAREST (stampede) vs TRIAGE (balanced)
    from backend.app.sim.entities import Patient

    hospitals_demo = [
        Hospital(
            id="mri",
            name="Manchester Royal Infirmary",
            lat=53.4626,
            lon=-2.2261,
            node_id=0,
            beds_total=10,
            beds_occupied=9,  # Only 1 bed left
            base_wait_min=10.0,
            service_min=10.0,
            specialties={"cardiac", "trauma", "general"},
            theatre_ready=True,
        ),
        Hospital(
            id="salford",
            name="Salford Royal",
            lat=53.4876,
            lon=-2.3234,
            node_id=1,
            beds_total=12,
            beds_occupied=5,  # 7 beds free
            base_wait_min=6.0,
            service_min=7.0,
            specialties={"cardiac", "trauma", "stroke", "general"},
            theatre_ready=True,
        ),
        Hospital(
            id="wyth",
            name="Wythenshawe Hospital",
            lat=53.3887,
            lon=-2.2931,
            node_id=2,
            beds_total=12,
            beds_occupied=7,  # 5 beds free
            base_wait_min=7.0,
            service_min=8.0,
            specialties={"cardiac", "burns", "general"},
            theatre_ready=True,
        ),
    ]

    ambulances_demo = [
        Ambulance(
            id=f"amb_{i+1}",
            patient=Patient(
                id=f"p_{i+1}",
                condition_id="stemi",
                age=62 + i,
                severity_s0=70.0,
                deterioration_rate_per_min=1.3,
                needs_specialty="cardiac",
                needs_theatre=False,
            ),
            current_node_id=20 + i,
        )
        for i in range(6)
    ]

    # All 6 central Manchester ambulances are 9 min from MRI, 13 min from Salford, 15 min from Wythenshawe
    demo_matrix = {
        amb.id: {"mri": 9.0, "salford": 13.0, "wyth": 15.0}
        for amb in ambulances_demo
    }

    nearest_map = assign_nearest(ambulances_demo, hospitals_demo, demo_matrix)
    triage_map = assign_triage(ambulances_demo, hospitals_demo, demo_matrix)

    print("=" * 72)
    print("TRIAGE — Policy Comparison Self-Test (6 Ambulances in Central Manchester)")
    print("=" * 72)
    print(f"NEAREST (Naive)   : {nearest_map}")
    print(f"TRIAGE  (Optimal) : {triage_map}")
    print("=" * 72)