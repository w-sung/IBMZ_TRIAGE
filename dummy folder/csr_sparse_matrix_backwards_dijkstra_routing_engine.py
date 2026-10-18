"""
TRIAGE — CSR Sparse Graph & Backwards Dijkstra Routing Engine (Chunk 2)

Implements CONTEXT.md Section 6.1 & Section 4 (s390x gotchas):
  - Loads data/nodes.csv, data/edges.csv, and data/hospitals.json
  - Deduplicates parallel (u, v) edges to their MINIMUM base travel time before
    constructing the scipy.sparse.csr_matrix (because CSR sums duplicate entries!)
  - Runs backwards Dijkstra from all 8 hospitals simultaneously on the transposed
    CSR graph: `dijkstra(G.T.tocsr(), directed=True, indices=hospital_nodes, return_predecessors=True)`
  - Reconstructs full node paths and [lat, lon] coordinate polylines for Leaflet.js
"""

import csv
import json
import math
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

from backend.app.sim.traffic import Roadblock, TrafficModel


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"


class RoutingGraph:
    """
    High-performance road routing graph backed by scipy.sparse.csr_matrix
    and backwards Dijkstra from all hospitals.
    """

    def __init__(
        self,
        nodes_path: Optional[Path] = None,
        edges_path: Optional[Path] = None,
        hospitals_path: Optional[Path] = None,
        seed: int = 42,
    ) -> None:
        self.nodes_path = nodes_path or self._resolve_file("nodes.csv")
        self.edges_path = edges_path or self._resolve_file("edges.csv")
        self.hospitals_path = hospitals_path or (DATA_DIR / "hospitals.json")
        self.seed = seed

        # Node lookup structures
        self.node_coords: Dict[int, Tuple[float, float]] = {}
        self.num_nodes: int = 0

        # Hospital lookup structures
        self.hospitals: List[Dict[str, Any]] = []
        self.hospital_ids: List[str] = []
        self.hospital_nodes: List[int] = []
        self.hospital_index_by_id: Dict[str, int] = {}

        # Deduplicated edge arrays
        self.edge_u: np.ndarray = np.empty(0, dtype=np.int32)
        self.edge_v: np.ndarray = np.empty(0, dtype=np.int32)
        self.edge_length_m: np.ndarray = np.empty(0, dtype=np.float64)
        self.edge_speed_kph: np.ndarray = np.empty(0, dtype=np.float64)
        self.edge_base_seconds: np.ndarray = np.empty(0, dtype=np.float64)
        self.edge_road_classes: List[str] = []
        self.edge_mid_lats: np.ndarray = np.empty(0, dtype=np.float64)
        self.edge_mid_lons: np.ndarray = np.empty(0, dtype=np.float64)
        self.edge_index_by_pair: Dict[Tuple[int, int], int] = {}
        self.raw_edges_count: int = 0
        self.deduped_edges_count: int = 0

        self._load_nodes()
        self._load_hospitals()
        self._load_and_dedupe_edges()

        self.traffic_model = TrafficModel(
            edge_u=self.edge_u,
            edge_v=self.edge_v,
            edge_road_classes=self.edge_road_classes,
            edge_mid_lats=self.edge_mid_lats,
            edge_mid_lons=self.edge_mid_lons,
            seed=self.seed,
        )

    @staticmethod
    def _resolve_file(filename: str) -> Path:
        """Check data/<filename> first, then fallback to data/graph/<filename>."""
        primary = DATA_DIR / filename
        if primary.exists():
            return primary
        fallback = DATA_DIR / "graph" / filename
        if fallback.exists():
            return fallback
        return primary

    def _load_nodes(self) -> None:
        if not self.nodes_path.exists():
            raise FileNotFoundError(
                f"Road nodes file not found at {self.nodes_path}. "
                "Run `python scripts/build_graph.py` first."
            )
        with self.nodes_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                nid = int(row["id"])
                lat = float(row["lat"])
                lon = float(row["lon"])
                self.node_coords[nid] = (lat, lon)

        self.num_nodes = max(self.node_coords.keys()) + 1 if self.node_coords else 0

    def _load_hospitals(self) -> None:
        if not self.hospitals_path.exists():
            raise FileNotFoundError(
                f"Hospitals file not found at {self.hospitals_path}."
            )
        with self.hospitals_path.open("r", encoding="utf-8") as f:
            self.hospitals = json.load(f)

        self.hospital_ids = []
        self.hospital_nodes = []
        self.hospital_index_by_id = {}

        for idx, hosp in enumerate(self.hospitals):
            hid = str(hosp["id"])
            node_id = int(hosp.get("node_id", idx))
            if node_id not in self.node_coords:
                node_id = self.nearest_node(float(hosp["lat"]), float(hosp["lon"]))
                hosp["node_id"] = node_id
            self.hospital_ids.append(hid)
            self.hospital_nodes.append(node_id)
            self.hospital_index_by_id[hid] = idx

    def _load_and_dedupe_edges(self) -> None:
        """
        Load edges.csv and deduplicate any parallel (u, v) edges to the edge with
        the MINIMUM base travel time in seconds.
        Critical per CONTEXT.md Section 4: scipy.sparse.csr_matrix sums duplicate
        (row, col) entries if not deduplicated first.
        """
        if not self.edges_path.exists():
            raise FileNotFoundError(
                f"Road edges file not found at {self.edges_path}. "
                "Run `python scripts/build_graph.py` first."
            )

        best_edges: Dict[Tuple[int, int], Dict[str, Any]] = {}
        raw_count = 0

        with self.edges_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                raw_count += 1
                u = int(row["u"])
                v = int(row["v"])
                if u == v:
                    continue
                length_m = float(row["length_m"])
                speed_kph = max(5.0, float(row["speed_kph"]))
                speed_mps = speed_kph / 3.6
                base_seconds = length_m / speed_mps
                road_class = str(row.get("road_class", "secondary"))

                key = (u, v)
                if key not in best_edges or base_seconds < best_edges[key]["base_seconds"]:
                    best_edges[key] = {
                        "u": u,
                        "v": v,
                        "length_m": length_m,
                        "speed_kph": speed_kph,
                        "base_seconds": base_seconds,
                        "road_class": road_class,
                    }

        self.raw_edges_count = raw_count
        self.deduped_edges_count = len(best_edges)

        u_list: List[int] = []
        v_list: List[int] = []
        len_list: List[float] = []
        spd_list: List[float] = []
        sec_list: List[float] = []
        rc_list: List[str] = []
        mid_lats: List[float] = []
        mid_lons: List[float] = []

        for idx, ((u, v), edata) in enumerate(best_edges.items()):
            u_list.append(u)
            v_list.append(v)
            len_list.append(edata["length_m"])
            spd_list.append(edata["speed_kph"])
            sec_list.append(edata["base_seconds"])
            rc_list.append(edata["road_class"])

            lat_u, lon_u = self.node_coords[u]
            lat_v, lon_v = self.node_coords[v]
            mid_lats.append((lat_u + lat_v) * 0.5)
            mid_lons.append((lon_u + lon_v) * 0.5)
            self.edge_index_by_pair[(u, v)] = idx

        self.edge_u = np.asarray(u_list, dtype=np.int32)
        self.edge_v = np.asarray(v_list, dtype=np.int32)
        self.edge_length_m = np.asarray(len_list, dtype=np.float64)
        self.edge_speed_kph = np.asarray(spd_list, dtype=np.float64)
        self.edge_base_seconds = np.asarray(sec_list, dtype=np.float64)
        self.edge_road_classes = rc_list
        self.edge_mid_lats = np.asarray(mid_lats, dtype=np.float64)
        self.edge_mid_lons = np.asarray(mid_lons, dtype=np.float64)

    def build_csr_matrix(
        self,
        congestion_multipliers: Optional[np.ndarray] = None,
    ) -> csr_matrix:
        """
        Build a (num_nodes x num_nodes) scipy.sparse.csr_matrix where each edge weight
        is `base_seconds / congestion_multiplier`.
        """
        if congestion_multipliers is None:
            weights = self.edge_base_seconds.copy()
        else:
            safe_mult = np.clip(congestion_multipliers, 0.01, 1.0)
            weights = self.edge_base_seconds / safe_mult

        return csr_matrix(
            (weights, (self.edge_u, self.edge_v)),
            shape=(self.num_nodes, self.num_nodes),
            dtype=np.float64,
        )

    def compute_travel_times(
        self,
        traffic_level: str | float = "normal",
        hour_of_day: Optional[float] = None,
        roadblocks: Optional[List[Roadblock]] = None,
        congestion_multipliers: Optional[np.ndarray] = None,
        sim_time_s: float = 0.0,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Run backwards Dijkstra from all hospital nodes on the transposed CSR graph.
        Returns:
          - times_to_hosp: shape (num_hospitals, num_nodes) in seconds
          - predecessors : shape (num_hospitals, num_nodes) node IDs for path reconstruction
        """
        if congestion_multipliers is None:
            congestion_multipliers = self.traffic_model.compute_multipliers(
                traffic_level=traffic_level,
                hour_of_day=hour_of_day,
                roadblocks=roadblocks,
                ambulance_lights_sirens=True,
                sim_time_s=sim_time_s,
            )

        G_csr = self.build_csr_matrix(congestion_multipliers)
        times_to_hosp, pred = dijkstra(
            G_csr.T.tocsr(),
            directed=True,
            indices=self.hospital_nodes,
            return_predecessors=True,
        )
        return times_to_hosp, pred

    def reconstruct_path(
        self,
        hospital_idx_or_id: int | str,
        start_node: int,
        predecessors: np.ndarray,
    ) -> List[int]:
        """
        Follow `predecessors[h_idx, :]` from `start_node` to `hospital_nodes[h_idx]`.
        Because Dijkstra was run on the transposed graph `G.T`, `pred[h_idx, curr]`
        gives the exact next forward node along the shortest path toward hospital `h_idx`!
        """
        if isinstance(hospital_idx_or_id, str):
            h_idx = self.hospital_index_by_id[hospital_idx_or_id]
        else:
            h_idx = int(hospital_idx_or_id)

        target_node = self.hospital_nodes[h_idx]
        if start_node == target_node:
            return [start_node]

        path: List[int] = [ int(start_node) ]
        curr = int(start_node)
        max_steps = self.num_nodes + 5

        for _ in range(max_steps):
            if curr == target_node:
                break
            nxt = int(predecessors[h_idx, curr])
            if nxt < 0 or nxt == curr:
                break
            path.append(nxt)
            curr = nxt

        return path

    def reconstruct_route_coords(
        self,
        hospital_idx_or_id: int | str,
        start_node: int,
        predecessors: np.ndarray,
    ) -> List[List[float]]:
        """
        Return the list of `[lat, lon]` coordinates along the optimal route
        from `start_node` to the specified hospital for Leaflet.js polyline rendering.
        """
        node_path = self.reconstruct_path(hospital_idx_or_id, start_node, predecessors)
        return [
            [self.node_coords[nid][0], self.node_coords[nid][1]]
            for nid in node_path
            if nid in self.node_coords
        ]

    def nearest_node(self, lat: float, lon: float) -> int:
        """Find the closest road graph node ID to any (lat, lon) coordinate."""
        best_nid = 0
        best_dist = float("inf")
        for nid, (nlat, nlon) in self.node_coords.items():
            d = (nlat - lat) ** 2 + ((nlon - lon) * math.cos(math.radians(lat))) ** 2
            if d < best_dist:
                best_dist = d
                best_nid = nid
        return best_nid


if __name__ == "__main__":
    t0 = time.perf_counter()
    rg = RoutingGraph()
    load_ms = (time.perf_counter() - t0) * 1000.0

    t1 = time.perf_counter()
    times_sec, preds = rg.compute_travel_times(traffic_level="normal", hour_of_day=20.37)
    dijkstra_ms = (time.perf_counter() - t1) * 1000.0

    times_rush, _ = rg.compute_travel_times(traffic_level="rush_hour", hour_of_day=8.5)

    print("=" * 72)
    print("TRIAGE — CSR Routing Engine & Backwards Dijkstra Self-Test")
    print("=" * 72)
    print(f"Nodes loaded               : {rg.num_nodes}")
    print(
        f"Edges loaded (deduplicated): {rg.deduped_edges_count} "
        f"(removed {rg.raw_edges_count - rg.deduped_edges_count} parallel duplicates)"
    )
    print(f"Graph load time            : {load_ms:.2f} ms")
    print(f"8-Hospital Dijkstra time   : {dijkstra_ms:.2f} ms (Target: < 100 ms)")
    print("-" * 72)
    sample_node = 25
    s_lat, s_lon = rg.node_coords[sample_node]
    print(f"Sample Ambulance at Node {sample_node} ({s_lat:.4f}, {s_lon:.4f}):")
    for h_idx, hosp in enumerate(rg.hospitals):
        eta_quiet_min = times_sec[h_idx, sample_node] / 60.0
        eta_rush_min = times_rush[h_idx, sample_node] / 60.0
        path_nodes = rg.reconstruct_path(h_idx, sample_node, preds)
        print(
            f"  -> {hosp['name']:<34} | 8:22 PM: {eta_quiet_min:>5.1f} min | "
            f"Rush Hour: {eta_rush_min:>5.1f} min | Hops: {len(path_nodes)}"
        )
    print("=" * 72)