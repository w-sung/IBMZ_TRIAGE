"""Hospital-by-node travel times via backwards Dijkstra, plus path reconstruction."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.sparse.csgraph import dijkstra

from .graph import RoadGraph


class TravelEngine:
    def __init__(self, graph: RoadGraph, hospital_nodes) -> None:
        self.g = graph
        self.hospital_nodes = np.asarray(hospital_nodes, dtype=np.int64)
        self._edge_of = {(int(a), int(b)): i for i, (a, b) in enumerate(zip(graph.u, graph.v))}
        self.weights = graph.base_s.copy()
        self.times = np.empty((0, 0))
        self.pred = np.empty((0, 0), dtype=np.int32)

    def travel_times(self, multiplier: np.ndarray | None = None) -> np.ndarray:
        """times[h, node] = seconds from node to hospital h. multiplier is per edge (1 = free flow)."""
        m = np.ones(len(self.g.u)) if multiplier is None else np.clip(multiplier, 1e-3, None)
        self.weights = self.g.base_s / m
        gt = self.g.csr(self.weights).T.tocsr()  # reverse graph: one search per hospital
        self.times, self.pred = dijkstra(gt, directed=True, indices=self.hospital_nodes,
                                         return_predecessors=True)
        return self.times

    def path(self, h: int, node: int) -> list[int]:
        """Node indices from `node` to hospital h ([] if unreachable). Needs travel_times() first."""
        target, p = int(self.hospital_nodes[h]), [int(node)]
        while p[-1] != target:
            nxt = int(self.pred[h, p[-1]])
            if nxt < 0:
                return []
            p.append(nxt)
        return p

    def path_latlon(self, h: int, node: int) -> list[tuple[float, float]]:
        nodes, pts = self.path(h, node), []
        for a, b in zip(nodes, nodes[1:]):
            seg = self.g.geometry[self._edge_of[(a, b)]]
            pts.extend(seg if not pts else seg[1:])
        return pts or ([(float(self.g.lat[node]), float(self.g.lon[node]))] if nodes else [])


def load_hospitals(path: str | Path, graph: RoadGraph) -> list[dict]:
    """Hospitals with a resolved OSM node. Unresolved ones are dropped (outside the map area)."""
    items = json.loads(Path(path).read_text())["hospitals"]
    out = []
    for h in items:
        if h.get("node_id") is not None and int(h["node_id"]) in graph._idx:
            out.append({**h, "node_idx": graph.index_of(h["node_id"])})
    if not out:
        raise ValueError("No hospital has a node_id on this graph. Run scripts/build_graph.py (WSL) first.")
    return out
