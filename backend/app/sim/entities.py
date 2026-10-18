"""
TRIAGE — Simulation Entities & State Dataclasses (Chunk 4)

Implements CONTEXT.md Section 6.4:
  - Hospital: id, name, lat, lon, node_id, beds_total, beds_occupied,
    base_wait_min, service_min, specialties (set), theatre_ready (bool),
    inbound (list of ambulance IDs), plus stress_level (0 to 100).
  - Patient: id, condition_id, age, severity_s0, deterioration_rate_per_min,
    needs_specialty, needs_theatre (plus optional sex & vitals for UI/notes).
  - Ambulance: id, patient, current_node_id, status (EN_ROUTE, QUEUED_AT_HOSPITAL,
    HANDOVER_DONE), destination_hospital_id, and live tracking fields for the engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Hospital:
    """
    Represents one of the 8 Greater Manchester NHS emergency departments.
    """

    id: str
    name: str
    lat: float
    lon: float
    node_id: int
    beds_total: int
    beds_occupied: int
    base_wait_min: float
    service_min: float
    specialties: set[str] = field(default_factory=set)
    theatre_ready: bool = True
    inbound: list[str] = field(default_factory=list)
    queue: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Ensure specialties is always a Python set[str] even if loaded from a JSON list
        if not isinstance(self.specialties, set):
            self.specialties = {str(s).lower() for s in self.specialties}
        else:
            self.specialties = {str(s).lower() for s in self.specialties}

    @property
    def beds_free(self) -> int:
        """Number of immediately available emergency beds (never negative)."""
        return max(0, int(self.beds_total) - int(self.beds_occupied))

    @property
    def stress_level(self) -> float:
        """
        Hospital stress level scaled 0.0 to 100.0 based on current bed occupancy,
        inbound ambulances en route, and any queued patients waiting for handover.
        """
        total_capacity = max(1, int(self.beds_total))
        occupancy_ratio = max(0.0, float(self.beds_occupied)) / total_capacity
        inbound_load_ratio = (len(self.inbound) + len(self.queue)) / total_capacity

        # Weighted blend: 65% current bed occupancy + 35% incoming/queued pressure,
        # plus a pressure bump if no free beds remain.
        raw_stress = (occupancy_ratio * 65.0) + (inbound_load_ratio * 85.0)
        if self.beds_free == 0 and (len(self.inbound) > 0 or len(self.queue) > 0):
            raw_stress += 15.0

        return round(min(100.0, max(0.0, raw_stress)), 1)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Hospital:
        """Construct a Hospital instance cleanly from a data/hospitals.json entry."""
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            lat=float(data["lat"]),
            lon=float(data["lon"]),
            node_id=int(data.get("node_id", 0)),
            beds_total=int(data.get("beds_total", 12)),
            beds_occupied=int(data.get("beds_occupied", 8)),
            base_wait_min=float(data.get("base_wait_min", 10.0)),
            service_min=float(data.get("service_min", 8.0)),
            specialties={str(s).lower() for s in data.get("specialties", [])},
            theatre_ready=bool(data.get("theatre_ready", True)),
            inbound=list(data.get("inbound", [])),
            queue=list(data.get("queue", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize hospital state for REST and WebSocket messages."""
        return {
            "id": self.id,
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "node_id": self.node_id,
            "beds_total": self.beds_total,
            "beds_occupied": self.beds_occupied,
            "beds_free": self.beds_free,
            "base_wait_min": self.base_wait_min,
            "service_min": self.service_min,
            "specialties": sorted(self.specialties),
            "theatre_ready": self.theatre_ready,
            "inbound": list(self.inbound),
            "inbound_count": len(self.inbound),
            "queue_count": len(self.queue),
            "stress": self.stress_level,
        }


@dataclass
class Patient:
    """
    Represents a patient on board an ambulance with AI-predicted starting severity (S0)
    and deterministic deterioration rate per minute.
    """

    id: str
    condition_id: str
    age: int
    severity_s0: float
    deterioration_rate_per_min: float
    needs_specialty: str | None = None
    needs_theatre: bool = False
    sex: str = "M"
    condition_name: str = ""
    vitals: dict[str, Any] = field(default_factory=dict)

    def deterioration_at(self, elapsed_minutes: float) -> float:
        """
        Compute expected severity score D(t) = min(100, S0 + rate * t)
        after `elapsed_minutes`.
        """
        score = float(self.severity_s0) + (
            float(self.deterioration_rate_per_min) * max(0.0, float(elapsed_minutes))
        )
        return round(min(100.0, max(0.0, score)), 2)

    @property
    def category(self) -> int:
        """NHS Response Category (1 to 4) based on current baseline severity S0."""
        if self.severity_s0 >= 75.0:
            return 1
        if self.severity_s0 >= 50.0:
            return 2
        if self.severity_s0 >= 25.0:
            return 3
        return 4


@dataclass
class Ambulance:
    """
    Represents an active emergency ambulance in the simulation.
    Status values per CONTEXT.md Section 6.6:
      - "EN_ROUTE"
      - "QUEUED_AT_HOSPITAL"
      - "HANDOVER_DONE"
    """

    id: str
    patient: Patient
    current_node_id: int
    status: str = "EN_ROUTE"
    destination_hospital_id: str | None = None

    # Additional positional/simulation fields used by the engine and WebSocket stream
    lat: float = 53.4808
    lon: float = -2.2426
    heading_deg: float = 0.0
    eta_seconds: float = 0.0
    elapsed_minutes: float = 0.0
    route_nodes: list[int] = field(default_factory=list)
    route_coords: list[list[float]] = field(default_factory=list)
    handover_note: str = ""

    @property
    def current_deterioration(self) -> float:
        """Live deterioration score D(t) based on elapsed minutes since pickup."""
        return self.patient.deterioration_at(self.elapsed_minutes)