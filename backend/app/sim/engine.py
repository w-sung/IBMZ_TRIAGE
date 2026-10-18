"""
===============================================================================
TRIAGE — 1-Second Tick Simulation Engine & Impact Calculator
Full complete file — Select All (Ctrl+A) and Paste (Ctrl+V) into:
backend/app/sim/engine.py
===============================================================================
"""

from __future__ import annotations

import json
import math
from typing import Any

import numpy as np

from backend.app.guidance.assign import lookup_drive_minutes
from backend.app.guidance.policies import apply_policy
from backend.app.sim.entities import Ambulance, Hospital, Patient

# National baseline figures from CONTEXT.md Section 1 & Section 5.1 (AACE 2025)
BASELINE_HANDOVER_WAIT_MIN: float = 30.0
ANNUAL_SEVERE_HARM_BASELINE: int = 44_000
COMMIT_RADIUS_SECONDS: float = 180.0


def _compute_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate compass heading in degrees [0, 360) from point 1 to point 2."""
    if abs(lat1 - lat2) < 1e-9 and abs(lon1 - lon2) < 1e-9:
        return 0.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_lon = math.radians(lon2 - lon1)
    y = math.sin(d_lon) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lon)
    bearing = math.degrees(math.atan2(y, x))
    return round((bearing + 360.0) % 360.0, 1)


class SimulationEngine:
    """
    Server-authoritative 1-second step simulation engine for TRIAGE.
    """

    def __init__(
        self,
        hospitals: list[Hospital],
        ambulances: list[Ambulance],
        travel_time_matrix: dict[Any, Any] | np.ndarray,
        policy_name: str = "TRIAGE",
    ) -> None:
        self.hospitals: list[Hospital] = hospitals
        self.ambulances: list[Ambulance] = ambulances
        self.travel_time_matrix: dict[Any, Any] | np.ndarray = travel_time_matrix
        self.policy_name: str = str(policy_name).strip().upper()

        self.sim_time_s: int = 0
        self.running: bool = True
        self.events: list[dict[str, Any]] = []

        self._hospital_by_id: dict[str, Hospital] = {h.id: h for h in self.hospitals}
        self._hospital_idx_by_id: dict[str, int] = {
            h.id: idx for idx, h in enumerate(self.hospitals)
        }
        self._ambulance_idx_by_id: dict[str, int] = {
            a.id: idx for idx, a in enumerate(self.ambulances)
        }

        self._initial_eta_s: dict[str, float] = {}
        self._start_coords: dict[str, tuple[float, float]] = {
            a.id: (float(a.lat), float(a.lon)) for a in self.ambulances
        }
        self._queue_remaining_s: dict[str, float] = {}
        self._route_updated_this_tick: set[str] = set()

        self._initialize_assignments()

    def _initialize_assignments(self) -> None:
        """Ensure all ambulances have an initial destination and valid ETA at t=0."""
        en_route = [a for a in self.ambulances if a.status == "EN_ROUTE"]
        if not en_route:
            return

        needs_assignment = any(a.destination_hospital_id is None for a in en_route)
        if needs_assignment:
            initial_map = apply_policy(
                policy_name=self.policy_name,
                ambulances=en_route,
                hospitals=self.hospitals,
                travel_time_matrix=self.travel_time_matrix,
            )
            for amb in en_route:
                if amb.destination_hospital_id is None and amb.id in initial_map:
                    amb.destination_hospital_id = initial_map[amb.id]
                    self.events.append(
                        {
                            "t": self.sim_time_s,
                            "kind": "assignment",
                            "ambulance_id": amb.id,
                            "to": amb.destination_hospital_id,
                        }
                    )

        for amb in en_route:
            hosp_id = amb.destination_hospital_id
            if hosp_id and hosp_id in self._hospital_by_id:
                hosp = self._hospital_by_id[hosp_id]
                if amb.eta_seconds <= 0.0:
                    drive_min = lookup_drive_minutes(
                        travel_time_matrix=self.travel_time_matrix,
                        ambulance=amb,
                        hospital=hosp,
                        amb_idx=self._ambulance_idx_by_id[amb.id],
                        hosp_idx=self._hospital_idx_by_id[hosp.id],
                    )
                    amb.eta_seconds = max(1.0, round(drive_min * 60.0))

                self._initial_eta_s[amb.id] = max(1.0, float(amb.eta_seconds))
                if not amb.route_coords:
                    amb.route_coords = [
                        [float(amb.lat), float(amb.lon)],
                        [float(hosp.lat), float(hosp.lon)],
                    ]
                if not amb.handover_note:
                    amb.handover_note = self._build_template_note(amb, hosp)
                self._route_updated_this_tick.add(amb.id)

        self._sync_hospital_inbound_lists()

    def _build_template_note(self, amb: Ambulance, hosp: Hospital) -> str:
        """Fallback clinical handover note per CONTEXT.md Section 6.7."""
        p = amb.patient
        sex_label = "female" if str(p.sex).upper() == "F" else "male"
        cond_label = p.condition_name or p.condition_id.replace("_", " ")
        eta_min = max(1, int(round(amb.eta_seconds / 60.0)))
        curr_det = amb.current_deterioration
        spec_text = (
            f"{p.needs_specialty.capitalize()} team needed."
            if p.needs_specialty and p.needs_specialty not in ("none", "")
            else "Standard ED bay needed."
        )
        return (
            f"{p.age}-year-old {sex_label}, suspected {cond_label}. "
            f"Category {p.category}, deterioration {curr_det:.1f} and rising "
            f"{p.deterioration_rate_per_min:.1f} per minute. "
            f"ETA {eta_min} min to {hosp.name}. {spec_text}"
        )

    def _sync_hospital_inbound_lists(self) -> None:
        """Keep `hospital.inbound` synchronized with currently EN_ROUTE ambulances."""
        for hosp in self.hospitals:
            hosp.inbound = []
        for amb in self.ambulances:
            if amb.status == "EN_ROUTE" and amb.destination_hospital_id in self._hospital_by_id:
                self._hospital_by_id[amb.destination_hospital_id].inbound.append(amb.id)

    def _replan_assignments(self) -> None:
        """
        Execute the 15-second rolling replan using `apply_policy`.
        If an ambulance's assigned hospital changes, log a 'diversion' event.
        """
        en_route = [a for a in self.ambulances if a.status == "EN_ROUTE"]
        if not en_route:
            return

        pre_committed: dict[str, int] = {
            h.id: len(h.queue) for h in self.hospitals
        }

        new_assignments = apply_policy(
            policy_name=self.policy_name,
            ambulances=en_route,
            hospitals=self.hospitals,
            travel_time_matrix=self.travel_time_matrix,
            pre_committed_slots=pre_committed,
        )

        for amb in en_route:
            old_hosp_id = amb.destination_hospital_id
            new_hosp_id = new_assignments.get(amb.id, old_hosp_id)

            if new_hosp_id is None or new_hosp_id not in self._hospital_by_id:
                continue

            if old_hosp_id is not None and new_hosp_id != old_hosp_id:
                amb.destination_hospital_id = new_hosp_id
                new_hosp = self._hospital_by_id[new_hosp_id]

                drive_min = lookup_drive_minutes(
                    travel_time_matrix=self.travel_time_matrix,
                    ambulance=amb,
                    hospital=new_hosp,
                    amb_idx=self._ambulance_idx_by_id[amb.id],
                    hosp_idx=self._hospital_idx_by_id[new_hosp.id],
                )
                amb.eta_seconds = max(1.0, round(drive_min * 60.0))
                self._initial_eta_s[amb.id] = amb.eta_seconds
                self._start_coords[amb.id] = (float(amb.lat), float(amb.lon))
                amb.route_coords = [
                    [float(amb.lat), float(amb.lon)],
                    [float(new_hosp.lat), float(new_hosp.lon)],
                ]
                amb.handover_note = self._build_template_note(amb, new_hosp)
                self._route_updated_this_tick.add(amb.id)

                self.events.append(
                    {
                        "t": self.sim_time_s,
                        "kind": "diversion",
                        "ambulance_id": amb.id,
                        "from": old_hosp_id,
                        "to": new_hosp_id,
                    }
                )
            elif old_hosp_id is None:
                amb.destination_hospital_id = new_hosp_id
                new_hosp = self._hospital_by_id[new_hosp_id]
                drive_min = lookup_drive_minutes(
                    travel_time_matrix=self.travel_time_matrix,
                    ambulance=amb,
                    hospital=new_hosp,
                    amb_idx=self._ambulance_idx_by_id[amb.id],
                    hosp_idx=self._hospital_idx_by_id[new_hosp.id],
                )
                amb.eta_seconds = max(1.0, round(drive_min * 60.0))
                self._initial_eta_s[amb.id] = amb.eta_seconds
                amb.handover_note = self._build_template_note(amb, new_hosp)
                self._route_updated_this_tick.add(amb.id)

        self._sync_hospital_inbound_lists()

    def _update_ambulance_position(self, amb: Ambulance) -> None:
        """
        Smoothly interpolate ambulance lat/lon and compass heading along its route
        as `eta_seconds` counts down toward 0.
        """
        hosp_id = amb.destination_hospital_id
        if not hosp_id or hosp_id not in self._hospital_by_id:
            return

        hosp = self._hospital_by_id[hosp_id]
        total_eta = max(1.0, self._initial_eta_s.get(amb.id, amb.eta_seconds + 1.0))
        progress = 1.0 - max(0.0, min(1.0, amb.eta_seconds / total_eta))

        if len(amb.route_coords) >= 2:
            n_pts = len(amb.route_coords)
            exact_idx = progress * (n_pts - 1)
            seg_idx = min(n_pts - 2, max(0, int(math.floor(exact_idx))))
            seg_frac = exact_idx - seg_idx

            p1 = amb.route_coords[seg_idx]
            p2 = amb.route_coords[seg_idx + 1]
            new_lat = float(p1[0]) + (float(p2[0]) - float(p1[0])) * seg_frac
            new_lon = float(p1[1]) + (float(p2[1]) - float(p1[1])) * seg_frac
            amb.heading_deg = _compute_bearing_deg(
                float(p1[0]), float(p1[1]), float(p2[0]), float(p2[1])
            )
            amb.lat = round(new_lat, 6)
            amb.lon = round(new_lon, 6)
        else:
            start_lat, start_lon = self._start_coords.get(amb.id, (amb.lat, amb.lon))
            new_lat = start_lat + (hosp.lat - start_lat) * progress
            new_lon = start_lon + (hosp.lon - start_lon) * progress
            amb.heading_deg = _compute_bearing_deg(start_lat, start_lon, hosp.lat, hosp.lon)
            amb.lat = round(new_lat, 6)
            amb.lon = round(new_lon, 6)

    def tick(self) -> dict[str, Any]:
        """
        Advance the simulation world by 1 simulated second.
        """
        self._route_updated_this_tick.clear()
        self.sim_time_s += 1

        for amb in self.ambulances:
            if amb.status != "HANDOVER_DONE":
                amb.elapsed_minutes += 1.0 / 60.0

        if self.sim_time_s % 15 == 0:
            self._replan_assignments()

        for amb in self.ambulances:
            if amb.status == "EN_ROUTE":
                amb.eta_seconds = max(0.0, float(amb.eta_seconds) - 1.0)
                self._update_ambulance_position(amb)

                if amb.eta_seconds <= 0.0:
                    amb.eta_seconds = 0.0
                    amb.status = "QUEUED_AT_HOSPITAL"

                    hosp_id = amb.destination_hospital_id
                    if hosp_id and hosp_id in self._hospital_by_id:
                        hosp = self._hospital_by_id[hosp_id]
                        amb.lat = round(float(hosp.lat), 6)
                        amb.lon = round(float(hosp.lon), 6)
                        amb.current_node_id = hosp.node_id

                        if amb.id in hosp.inbound:
                            hosp.inbound.remove(amb.id)

                        patients_ahead = len(hosp.queue)
                        hosp.queue.append(amb.id)

                        # Fast visual handover completion (8 to 15 simulated seconds)
                        # so no ambulance ever hangs on QUEUED at the end of a demo run!
                        self._queue_remaining_s[amb.id] = float(8 + patients_ahead * 4)

                    self.events.append(
                        {
                            "t": self.sim_time_s,
                            "kind": "arrival",
                            "ambulance_id": amb.id,
                            "hospital_id": hosp_id,
                        }
                    )

            elif amb.status == "QUEUED_AT_HOSPITAL":
                rem_s = self._queue_remaining_s.get(amb.id, 0.0) - 1.0
                self._queue_remaining_s[amb.id] = max(0.0, rem_s)
                if rem_s <= 0.0:
                    amb.status = "HANDOVER_DONE"
                    hosp_id = amb.destination_hospital_id
                    if hosp_id and hosp_id in self._hospital_by_id:
                        hosp = self._hospital_by_id[hosp_id]
                        if amb.id in hosp.queue:
                            hosp.queue.remove(amb.id)
                        hosp.beds_occupied = min(hosp.beds_total, hosp.beds_occupied + 1)
                    self.events.append(
                        {
                            "t": self.sim_time_s,
                            "kind": "treatment_start",
                            "ambulance_id": amb.id,
                            "hospital_id": hosp_id,
                        }
                    )

        self._sync_hospital_inbound_lists()

        # As soon as all ambulances have reached their assigned hospitals (none EN_ROUTE)
        # and completed their brief handover, stop the clock so the 44,000 Impact Modal pops up!
        if self.ambulances and all(a.status == "HANDOVER_DONE" for a in self.ambulances):
            self.running = False

        return self.get_state()

    def get_state(self) -> dict[str, Any]:
        ambulances_payload: list[dict[str, Any]] = []
        for amb in self.ambulances:
            route_val = (
                amb.route_coords if amb.id in self._route_updated_this_tick else None
            )
            ambulances_payload.append(
                {
                    "id": amb.id,
                    "lat": round(float(amb.lat), 6),
                    "lon": round(float(amb.lon), 6),
                    "heading_deg": round(float(amb.heading_deg), 1),
                    "status": amb.status,
                    "hospital_id": amb.destination_hospital_id,
                    "eta_s": int(round(amb.eta_seconds)),
                    "deterioration": amb.current_deterioration,
                    "rate_per_min": round(float(amb.patient.deterioration_rate_per_min), 2),
                    "category": amb.patient.category,
                    "route": route_val,
                    "note": amb.handover_note,
                }
            )

        hospitals_payload: list[dict[str, Any]] = []
        for hosp in self.hospitals:
            hospitals_payload.append(
                {
                    "id": hosp.id,
                    "name": hosp.name,
                    "lat": hosp.lat,
                    "lon": hosp.lon,
                    "beds_free": hosp.beds_free,
                    "beds_total": hosp.beds_total,
                    "beds_occupied": hosp.beds_occupied,
                    "queue": len(hosp.queue),
                    "inbound": len(hosp.inbound),
                    "stress": hosp.stress_level,
                }
            )

        return {
            "type": "tick",
            "sim_time_s": self.sim_time_s,
            "running": self.running,
            "ambulances": ambulances_payload,
            "hospitals": hospitals_payload,
            "events": list(self.events),
        }

    def calculate_impact_summary(self) -> dict[str, Any]:
        if not self.ambulances:
            return {
                "baseline_handover_min": BASELINE_HANDOVER_WAIT_MIN,
                "triage_avg_handover_min": 0.0,
                "baseline_annual_severe_cases": ANNUAL_SEVERE_HARM_BASELINE,
                "projected_annual_severe_cases": 0,
                "severe_cases_prevented": ANNUAL_SEVERE_HARM_BASELINE,
                "reduction_percent": 100.0,
            }

        handover_waits: list[float] = []
        slot_tracker: dict[str, int] = {h.id: 0 for h in self.hospitals}

        for amb in self.ambulances:
            h_id = amb.destination_hospital_id
            if h_id and h_id in self._hospital_by_id:
                hosp = self._hospital_by_id[h_id]
                k_slot = slot_tracker[h_id]
                slot_tracker[h_id] += 1
                wait_min = float(hosp.base_wait_min) + (k_slot * float(hosp.service_min))
                if k_slot >= hosp.beds_free:
                    wait_min += 30.0
                handover_waits.append(wait_min)
            else:
                handover_waits.append(BASELINE_HANDOVER_WAIT_MIN)

        avg_handover_min = float(np.mean(handover_waits))
        ratio = max(0.05, min(1.0, avg_handover_min / BASELINE_HANDOVER_WAIT_MIN))
        projected_cases = int(round(ANNUAL_SEVERE_HARM_BASELINE * ratio))
        cases_prevented = max(0, ANNUAL_SEVERE_HARM_BASELINE - projected_cases)
        reduction_pct = round((cases_prevented / ANNUAL_SEVERE_HARM_BASELINE) * 100.0, 1)

        return {
            "policy": self.policy_name,
            "baseline_handover_min": BASELINE_HANDOVER_WAIT_MIN,
            "triage_avg_handover_min": round(avg_handover_min, 1),
            "baseline_annual_severe_cases": ANNUAL_SEVERE_HARM_BASELINE,
            "projected_annual_severe_cases": projected_cases,
            "severe_cases_prevented": cases_prevented,
            "reduction_percent": reduction_pct,
        }