"""
TRIAGE — Dynamic Traffic & Roadblock Simulation Engine (Chunk 2)
Implements CONTEXT.md Section 6.2:
  - Congestion multiplier per edge between 0.15 and 1.0:
      1 - (level * time_of_day_curve * road_class_factor * fixed_noise_per_edge)
  - Dynamic time-of-day traffic curves (e.g., 8:22 PM quiet vs 10:00 AM busy vs 8:30 AM rush hour)
  - Ambulance lights-and-sirens advantage (ambulances feel only half the congestion slowdown)
  - User-placed roadblocks: edges within radius_m get multiplier 0.02, triggering instant replan
"""

from dataclasses import dataclass
from datetime import datetime
import hashlib
import math
from typing import Dict, List, Optional, Sequence

import numpy as np


# Base congestion intensity for named traffic levels
TRAFFIC_LEVEL_FACTORS: Dict[str, float] = {
    "off_peak": 0.20,
    "light": 0.25,
    "normal": 0.52,
    "moderate": 0.60,
    "rush_hour": 0.88,
    "heavy": 0.90,
    "gridlock": 0.98,
}

# Sensitivity of different road classes to urban congestion
ROAD_CLASS_CONGESTION_FACTOR: Dict[str, float] = {
    "motorway": 0.72,
    "trunk": 0.85,
    "primary": 0.95,
    "secondary": 0.88,
    "tertiary": 0.75,
    "unclassified": 0.65,
}


@dataclass
class Roadblock:
    """Represents a user-placed or incident roadblock on the Manchester map."""

    id: str
    lat: float
    lon: float
    radius_m: float = 450.0


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute distance in meters between two lat/lon points."""
    r_earth = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    return 2.0 * r_earth * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))


def time_of_day_curve(hour_of_day: Optional[float] = None) -> float:
    """
    Calculate a realistic urban traffic multiplier (between 0.30 and 1.0)
    based on the time of day (0.0 to 24.0 hours).
    - Morning peak around 08:00 - 09:30 ( ~0.95 - 1.00 )
    - Midday / 10:00 AM active daytime traffic ( ~0.75 - 0.82 )
    - Evening peak around 17:00 - 18:30 ( ~0.95 - 1.00 )
    - Evening 20:22 (8:22 PM) light traffic ( ~0.42 )
    - Overnight 01:00 - 05:00 quiet roads ( ~0.30 )
    """
    if hour_of_day is None:
        now = datetime.now()
        hour_of_day = now.hour + now.minute / 60.0

    h = float(hour_of_day) % 24.0

    # Double-Gaussian morning + evening rush hour + daytime plateau
    morning_peak = 0.62 * math.exp(-((h - 8.25) ** 2) / (2.0 * 1.35**2))
    midday_hum = 0.42 * math.exp(-((h - 13.0) ** 2) / (2.0 * 3.8**2))
    evening_peak = 0.65 * math.exp(-((h - 17.5) ** 2) / (2.0 * 1.50**2))

    raw = 0.30 + max(morning_peak, midday_hum, evening_peak)
    return float(max(0.30, min(1.0, raw)))


def deterministic_edge_noise(u: int, v: int, seed: int = 42) -> float:
    """
    Generate fixed, reproducible per-edge noise in [0.85, 1.15] so the same seed
    always produces the exact same traffic distribution across runs.
    """
    key = f"{seed}:{u}:{v}".encode("utf-8")
    digest = hashlib.blake2b(key, digest_size=4).digest()
    uint_val = int.from_bytes(digest, byteorder="big")
    unit = uint_val / 0xFFFFFFFF
    return 0.85 + 0.30 * unit


class TrafficModel:
    """
    Computes per-edge congestion multipliers for the Manchester road network.
    """

    def __init__(
        self,
        edge_u: Sequence[int],
        edge_v: Sequence[int],
        edge_road_classes: Sequence[str],
        edge_mid_lats: Sequence[float],
        edge_mid_lons: Sequence[float],
        seed: int = 42,
    ) -> None:
        self.num_edges = len(edge_u)
        self.seed = seed
        self.edge_u = np.asarray(edge_u, dtype=np.int32)
        self.edge_v = np.asarray(edge_v, dtype=np.int32)
        self.edge_mid_lats = np.asarray(edge_mid_lats, dtype=np.float64)
        self.edge_mid_lons = np.asarray(edge_mid_lons, dtype=np.float64)

        self.road_class_factors = np.array(
            [
                ROAD_CLASS_CONGESTION_FACTOR.get(str(rc).lower(), 0.80)
                for rc in edge_road_classes
            ],
            dtype=np.float64,
        )
        self.fixed_noise = np.array(
            [
                deterministic_edge_noise(int(u), int(v), seed=seed)
                for u, v in zip(edge_u, edge_v)
            ],
            dtype=np.float64,
        )

    def compute_multipliers(
        self,
        traffic_level: str | float = "normal",
        hour_of_day: Optional[float] = None,
        roadblocks: Optional[List[Roadblock]] = None,
        ambulance_lights_sirens: bool = True,
        sim_time_s: float = 0.0,
    ) -> np.ndarray:
        """
        Return a 1D numpy array of congestion multipliers for every deduplicated edge.
        - Standard traffic multiplier lies in [0.15, 1.0].
        - Ambulances with lights & sirens feel only half of the congestion slowdown.
        - Any edge within `radius_m` of an active Roadblock gets multiplier 0.02.
        """
        if isinstance(traffic_level, (int, float)):
            level_val = float(max(0.0, min(1.0, traffic_level)))
        else:
            level_val = TRAFFIC_LEVEL_FACTORS.get(str(traffic_level).lower(), 0.52)

        # If a named level is explicitly chosen (off_peak / normal / rush_hour),
        # blend it with the time-of-day curve so both manual slider and clock time work naturally.
        tod_val = time_of_day_curve(hour_of_day) if hour_of_day is not None else 0.85

        # Subtle slow deterministic drift over simulated time (Section 6.6)
        drift = 1.0 + 0.04 * math.sin(sim_time_s / 180.0)

        raw_slowdown = (
            level_val * tod_val * self.road_class_factors * self.fixed_noise * drift
        )
        raw_slowdown = np.clip(raw_slowdown, 0.0, 0.85)

        if ambulance_lights_sirens:
            # CONTEXT.md Section 6.2: "Ambulances feel only about half of the congestion slowdown"
            effective_slowdown = 0.50 * raw_slowdown
        else:
            effective_slowdown = raw_slowdown

        multipliers = np.clip(1.0 - effective_slowdown, 0.15, 1.0)

        # Apply active roadblocks (multiplier = 0.02 inside radius_m)
        if roadblocks:
            for rb in roadblocks:
                for idx in range(self.num_edges):
                    dist = haversine_distance_m(
                        rb.lat,
                        rb.lon,
                        float(self.edge_mid_lats[idx]),
                        float(self.edge_mid_lons[idx]),
                    )
                    if dist <= rb.radius_m:
                        multipliers[idx] = 0.02

        return multipliers


if __name__ == "__main__":
    # Quick standalone verification of TrafficModel
    sample_tm = TrafficModel(
        edge_u=[0, 1, 2],
        edge_v=[1, 2, 3],
        edge_road_classes=["motorway", "primary", "tertiary"],
        edge_mid_lats=[53.4626, 53.4808, 53.5191],
        edge_mid_lons=[-2.2261, -2.2426, -2.2272],
        seed=42,
    )
    m_evening = sample_tm.compute_multipliers("off_peak", hour_of_day=20.37)  # 8:22 PM
    m_morning = sample_tm.compute_multipliers("rush_hour", hour_of_day=8.50)  # 8:30 AM
    m_blocked = sample_tm.compute_multipliers(
        "normal",
        hour_of_day=10.0,
        roadblocks=[Roadblock(id="rb_1", lat=53.4808, lon=-2.2426, radius_m=500.0)],
    )
    print("TrafficModel self-test:")
    print(f"  8:22 PM Off-Peak multipliers : {np.round(m_evening, 3)}")
    print(f"  8:30 AM Rush-Hour multipliers: {np.round(m_morning, 3)}")
    print(f"  10:00 AM + Roadblock on Edge1: {np.round(m_blocked, 3)}")