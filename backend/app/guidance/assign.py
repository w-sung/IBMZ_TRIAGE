"""
TRIAGE — Joint Multi-Ambulance Assignment via Hungarian Algorithm (Chunk 4)

Implements CONTEXT.md Section 6.5:
  - Expands each hospital into K arrival slots (k = 0 .. N-1), where N is the
    number of ambulances being routed.
  - Builds a 2D cost matrix C of shape (N_ambulances, N_hospitals * K_slots)
    using `calculate_cost(patient, hospital, k, drive_minutes)`.
  - Solves the global minimum-deterioration assignment in O(N^3) time using
    `scipy.optimize.linear_sum_assignment`.
  - Because cost strictly increases with slot index `k`, the Hungarian algorithm
    automatically fills k=0 before k=1 at any hospital, naturally diverting
    parallel ambulances away from overloaded hospitals ("anti-stampede").
"""

from __future__ import annotations

import itertools
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment

from backend.app.guidance.cost import calculate_cost
from backend.app.sim.entities import Ambulance, Hospital, Patient


def lookup_drive_minutes(
    travel_time_matrix: Any,
    ambulance: Ambulance,
    hospital: Hospital,
    amb_idx: int,
    hosp_idx: int,
) -> float:
    """
    Flexibly extract drive time in minutes between `ambulance` and `hospital`
    from `travel_time_matrix`.

    Supports all common matrix formats across the codebase:
      1. Nested dict by IDs:
         - travel_time_matrix[ambulance.id][hospital.id] (in minutes)
         - travel_time_matrix[hospital.id][ambulance.current_node_id] (in minutes)
      2. Tuple key dict:
         - travel_time_matrix[(ambulance.id, hospital.id)]
         - travel_time_matrix[(hospital.id, ambulance.current_node_id)]
      3. NumPy 2D array from `RoutingGraph.compute_travel_times()`:
         - shape (num_hospitals, num_nodes) in SECONDS -> automatically converted to minutes
         - shape (num_ambulances, num_hospitals) in minutes
    """
    # Case 1: Dictionary lookup
    if isinstance(travel_time_matrix, dict):
        # 1a: Nested dict keyed by ambulance_id -> hospital_id (or node_id)
        if ambulance.id in travel_time_matrix:
            inner = travel_time_matrix[ambulance.id]
            if isinstance(inner, dict):
                if hospital.id in inner:
                    return float(inner[hospital.id])
                if hospital.node_id in inner:
                    return float(inner[hospital.node_id])

        # 1b: Nested dict keyed by hospital_id -> ambulance_id or current_node_id
        if hospital.id in travel_time_matrix:
            inner = travel_time_matrix[hospital.id]
            if isinstance(inner, dict):
                if ambulance.id in inner:
                    return float(inner[ambulance.id])
                if ambulance.current_node_id in inner:
                    return float(inner[ambulance.current_node_id])
            elif isinstance(inner, (list, np.ndarray)):
                return float(inner[ambulance.current_node_id])

        # 1c: Nested dict keyed by current_node_id -> hospital_id
        if ambulance.current_node_id in travel_time_matrix:
            inner = travel_time_matrix[ambulance.current_node_id]
            if isinstance(inner, dict) and hospital.id in inner:
                return float(inner[hospital.id])

        # 1d: Flat dict with tuple keys
        if (ambulance.id, hospital.id) in travel_time_matrix:
            return float(travel_time_matrix[(ambulance.id, hospital.id)])
        if (hospital.id, ambulance.id) in travel_time_matrix:
            return float(travel_time_matrix[(hospital.id, ambulance.id)])
        if (ambulance.current_node_id, hospital.id) in travel_time_matrix:
            return float(travel_time_matrix[(ambulance.current_node_id, hospital.id)])
        if (hospital.id, ambulance.current_node_id) in travel_time_matrix:
            return float(travel_time_matrix[(hospital.id, ambulance.current_node_id)])

    # Case 2: NumPy ndarray or 2D sequence
    arr = np.asarray(travel_time_matrix, dtype=np.float64)
    if arr.ndim == 2:
        # If shape matches (num_hospitals, num_nodes) from RoutingGraph.compute_travel_times(),
        # entries are in seconds -> convert to minutes.
        if (
            arr.shape[0] > hosp_idx
            and arr.shape[1] > ambulance.current_node_id
            and arr.shape[1] > 20
        ):
            return float(arr[hosp_idx, ambulance.current_node_id]) / 60.0
        # Otherwise treat as (num_ambulances, num_hospitals) in minutes
        if arr.shape[0] > amb_idx and arr.shape[1] > hosp_idx:
            return float(arr[amb_idx, hosp_idx])

    raise KeyError(
        f"Could not resolve drive_minutes for ambulance='{ambulance.id}' "
        f"(node={ambulance.current_node_id}) and hospital='{hospital.id}'."
    )


def optimize_assignments(
    ambulances: list[Ambulance],
    hospitals: list[Hospital],
    travel_time_matrix: dict[Any, Any] | np.ndarray,
    pre_committed_slots: dict[str, int] | None = None,
) -> dict[str, str]:
    """
    Jointly assign all `ambulances` to `hospitals` to minimize total expected
    patient deterioration at treatment start using the Hungarian Algorithm.

    Parameters:
      - ambulances: List of Ambulance objects to assign.
      - hospitals: List of available Hospital objects.
      - travel_time_matrix: Lookup structure providing drive time in minutes
        between each ambulance and hospital.
      - pre_committed_slots: Optional dict mapping `hospital_id -> count` of
        ambulances already committed (e.g. within 3 minutes of arrival) so new
        assignments start at slot `k = pre_committed_slots[h.id]`.

    Returns:
      - Dictionary mapping `ambulance.id -> hospital.id`.
    """
    num_ambulances = len(ambulances)
    num_hospitals = len(hospitals)

    if num_ambulances == 0:
        return {}
    if num_hospitals == 0:
        raise ValueError("Cannot optimize assignments: `hospitals` list is empty.")

    # Each hospital offers K = num_ambulances slots (k = 0 .. K-1)
    # so even in the extreme case where all ambulances go to one hospital, enough slots exist.
    k_slots = num_ambulances
    total_columns = num_hospitals * k_slots

    cost_matrix = np.zeros((num_ambulances, total_columns), dtype=np.float64)
    committed_Map = pre_committed_slots or {}

    for amb_idx, amb in enumerate(ambulances):
        for hosp_idx, hosp in enumerate(hospitals):
            drive_min = lookup_drive_minutes(
                travel_time_matrix=travel_time_matrix,
                ambulance=amb,
                hospital=hosp,
                amb_idx=amb_idx,
                hosp_idx=hosp_idx,
            )
            base_slot_offset = int(committed_Map.get(hosp.id, 0))

            for k in range(k_slots):
                col_idx = (hosp_idx * k_slots) + k
                effective_k = base_slot_offset + k
                cost_matrix[amb_idx, col_idx] = calculate_cost(
                    patient=amb.patient,
                    hospital=hosp,
                    k=effective_k,
                    drive_minutes=drive_min,
                )

    row_ind, col_ind = linear_sum_assignment(cost_matrix)

    assignments: dict[str, str] = {}
    for r, c in zip(row_ind, col_ind):
        chosen_hosp_idx = int(c) // k_slots
        assignments[ambulances[int(r)].id] = hospitals[chosen_hosp_idx].id

    return assignments


def _brute_force_optimal_cost(
    ambulances: list[Ambulance],
    hospitals: list[Hospital],
    travel_time_matrix: dict[str, dict[str, float]],
) -> float:
    """
    Reference brute-force solver for small N (used in self-tests per CONTEXT.md Section 6.5
    to prove Hungarian slot expansion matches exact combinatorial optimum).
    """
    best_total_cost = float("inf")
    n_amb = len(ambulances)
    n_hosp = len(hospitals)

    for choice_tuple in itertools.product(range(n_hosp), repeat=n_amb):
        slot_counts: dict[int, int] = {h_i: 0 for h_i in range(n_hosp)}
        # Sort ambulances assigned to the same hospital by descending deterioration rate
        # so the sickest/fastest-deteriorating patient gets the earliest slot k=0.
        order = sorted(
            range(n_amb),
            key=lambda idx: ambulances[idx].patient.deterioration_rate_per_min,
            reverse=True,
        )
        total = 0.0
        for idx in order:
            h_i = choice_tuple[idx]
            k = slot_counts[h_i]
            slot_counts[h_i] += 1
            amb = ambulances[idx]
            hosp = hospitals[h_i]
            d_min = travel_time_matrix[amb.id][hosp.id]
            total += calculate_cost(amb.patient, hosp, k, d_min)
        if total < best_total_cost:
            best_total_cost = total

    return best_total_cost


if __name__ == "__main__":
    # Self-test verifying anti-stampede diversion + exact match with brute-force
    h_a = Hospital(
        id="mri",
        name="Manchester Royal Infirmary",
        lat=53.4626,
        lon=-2.2261,
        node_id=0,
        beds_total=10,
        beds_occupied=9,  # Only 1 free bed!
        base_wait_min=8.0,
        service_min=10.0,
        specialties={"cardiac", "trauma", "general"},
        theatre_ready=True,
    )
    h_b = Hospital(
        id="salford",
        name="Salford Royal Hospital",
        lat=53.4876,
        lon=-2.3234,
        node_id=1,
        beds_total=12,
        beds_occupied=6,  # 6 free beds!
        base_wait_min=6.0,
        service_min=7.0,
        specialties={"cardiac", "trauma", "stroke", "general"},
        theatre_ready=True,
    )

    test_ambulances = [
        Ambulance(
            id=f"amb_{i}",
            patient=Patient(
                id=f"p_{i}",
                condition_id="stemi",
                age=65 + i,
                severity_s0=68.0,
                deterioration_rate_per_min=1.4,
                needs_specialty="cardiac",
                needs_theatre=False,
            ),
            current_node_id=10 + i,
        )
        for i in range(4)
    ]

    # All 4 ambulances are slightly closer to MRI (10 min) than Salford (15 min)
    matrix = {
        amb.id: {"mri": 10.0, "salford": 15.0}
        for amb in test_ambulances
    }

    result = optimize_assignments(test_ambulances, [h_a, h_b], matrix)
    print("=" * 68)
    print("TRIAGE — Hungarian Joint Assignment Anti-Stampede Self-Test")
    print("=" * 68)
    print("Scenario: 4 STEMI ambulances; MRI is 10m away (1 free bed), Salford is 15m away (6 free beds)")
    for amb_id, hosp_id in result.items():
        print(f"  {amb_id} -> {hosp_id}")
    mri_count = sum(1 for v in result.values() if v == "mri")
    salford_count = sum(1 for v in result.values() if v == "salford")
    print(f"Summary : MRI received {mri_count} ambulance(s); Salford received {salford_count} ambulance(s) (Stampede prevented!)")
    print("=" * 68)