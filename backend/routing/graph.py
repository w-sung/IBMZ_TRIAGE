"""Road graph loading. CSV only, never pickle (s390x is big-endian)."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix

CLASSES = ["motorway", "trunk", "primary", "secondary", "tertiary", "unclassified"]
M_PER_DEG = 111_320.0


@dataclass
class RoadGraph:
    node_ids: np.ndarray   # original OSM ids (N,)
    lat: np.ndarray
    lon: np.ndarray
    u: np.ndarray          # edge source, node INDEX (E,)
    v: np.ndarray          # edge target, node INDEX (E,)
    base_s: np.ndarray     # free-flow travel seconds (E,)
    road_class: np.ndarray # index into CLASSES (E,)
    geometry: list         # per edge: [(lat, lon), ...] running u -> v
    _idx: dict = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._idx = {int(i): k for k, i in enumerate(self.node_ids)}

    @property
    def n_nodes(self) -> int:
        return len(self.node_ids)

    def index_of(self, osm_id: int) -> int:
        return self._idx[int(osm_id)]

    def csr(self, seconds: np.ndarray) -> csr_matrix:
        """Edges are deduplicated at load, so csr_matrix never sums parallel roads."""
        n = self.n_nodes
        return csr_matrix((seconds, (self.u, self.v)), shape=(n, n))

    def metres_to(self, lat: float, lon: float, la: np.ndarray, lo: np.ndarray) -> np.ndarray:
        dy = (la - lat) * M_PER_DEG
        dx = (lo - lon) * M_PER_DEG * np.cos(np.radians(lat))
        return np.hypot(dx, dy)

    def edge_mid(self) -> tuple[np.ndarray, np.ndarray]:
        return (self.lat[self.u] + self.lat[self.v]) / 2, (self.lon[self.u] + self.lon[self.v]) / 2

    def nearest_node(self, lat: float, lon: float) -> int:
        return int(np.argmin(self.metres_to(lat, lon, self.lat, self.lon)))


def _geom(s: str, a: tuple, b: tuple) -> list:
    if s:
        pts = [tuple(map(float, p.split(","))) for p in s.split(";")]
        if len(pts) >= 2:
            return pts
    return [a, b]


def load_graph(graph_dir: str | Path) -> RoadGraph:
    d = Path(graph_dir)
    with open(d / "nodes.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    ids = np.array([int(r["id"]) for r in rows], dtype=np.int64)
    lat = np.array([float(r["lat"]) for r in rows])
    lon = np.array([float(r["lon"]) for r in rows])
    idx = {int(i): k for k, i in enumerate(ids)}

    eu, ev, base, cls, geo = [], [], [], [], []
    with open(d / "edges.csv", newline="") as f:
        for r in csv.DictReader(f):
            a, b = idx.get(int(r["u"])), idx.get(int(r["v"]))
            if a is None or b is None or a == b:
                continue
            speed = max(float(r["speed_kph"]), 5.0)
            eu.append(a); ev.append(b)
            base.append(max(float(r["length_m"]) / (speed / 3.6), 0.1))
            c = r["road_class"]
            cls.append(CLASSES.index(c) if c in CLASSES else len(CLASSES) - 1)
            geo.append(_geom(r.get("geometry", ""), (lat[a], lon[a]), (lat[b], lon[b])))

    u, v, base, cls = (np.array(x) for x in (eu, ev, base, cls))
    # Parallel roads: keep the fastest per (u, v). Do not let csr_matrix sum them.
    key = u.astype(np.int64) * len(ids) + v
    order = np.lexsort((base, key))
    k = key[order]
    keep = np.sort(order[np.r_[True, k[1:] != k[:-1]]])
    return RoadGraph(ids, lat, lon, u[keep], v[keep], base[keep], cls[keep], [geo[i] for i in keep])
