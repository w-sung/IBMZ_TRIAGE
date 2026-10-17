"""Simulated traffic (no external API). All numbers are tunable assumptions, not measurements."""
from __future__ import annotations

import numpy as np

from ..routing.graph import M_PER_DEG, RoadGraph

CLASS_FACTOR = np.array([1.0, 0.9, 0.8, 0.6, 0.45, 0.3])  # how jam-prone each road class is
LEVELS = {"off_peak": 0.3, "normal": 0.6, "rush_hour": 1.0}
AMBULANCE_FEELS = 0.5   # lights and sirens: only half the slowdown
BLOCKED = 0.02


def _bump(hour: float, mu: float, sigma: float) -> float:
    d = ((hour - mu + 12) % 24) - 12  # wrap around midnight
    return float(np.exp(-0.5 * (d / sigma) ** 2))


def time_of_day_curve(hour: float) -> float:
    """0..1 congestion shape: peaks about 08:30 and 17:30, quiet floor at night."""
    return min(1.0, 0.08 + 0.92 * max(_bump(hour, 8.5, 1.5), _bump(hour, 17.5, 1.75)))


def hospital_pressure(hour: float) -> float:
    """Multiplier on a hospital's base_wait_min: 0.75 (quiet) to 1.5 (busy). Assumption."""
    return 0.75 + 0.75 * time_of_day_curve(hour)


class TrafficModel:
    def __init__(self, graph: RoadGraph, seed: int = 42) -> None:
        self.g = graph
        self.noise = np.random.default_rng(seed).uniform(0.6, 1.0, len(graph.u))  # fixed per edge
        self.cf = CLASS_FACTOR[graph.road_class]

    def distance_to(self, lat: float, lon: float) -> np.ndarray:
        """Metres from a point to each edge's straight segment (not just its midpoint, so long
        roads are caught too)."""
        g, k = self.g, M_PER_DEG * np.cos(np.radians(lat))
        ax, ay = (g.lon[g.u] - lon) * k, (g.lat[g.u] - lat) * M_PER_DEG
        dx, dy = (g.lon[g.v] - g.lon[g.u]) * k, (g.lat[g.v] - g.lat[g.u]) * M_PER_DEG
        t = np.clip(-(ax * dx + ay * dy) / np.maximum(dx * dx + dy * dy, 1e-9), 0.0, 1.0)
        return np.hypot(ax + t * dx, ay + t * dy)

    def multiplier(self, level: float, hour: float | None = None,
                   roadblocks: list[tuple[float, float, float]] = (), ambulance: bool = True) -> np.ndarray:
        """Per-edge speed multiplier. hour=None means the slider alone drives it; otherwise the
        clock curve scales it. roadblocks are (lat, lon, radius_m)."""
        curve = 1.0 if hour is None else time_of_day_curve(hour)
        m = np.clip(1.0 - level * curve * self.cf * self.noise, 0.15, 1.0)
        if ambulance:
            m = 1.0 - AMBULANCE_FEELS * (1.0 - m)
        for lat, lon, r in roadblocks:
            m[self.distance_to(lat, lon) <= r] = BLOCKED
        return m
