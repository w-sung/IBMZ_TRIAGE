"""
===============================================================================
TRIAGE — High-Density Greater Manchester Street & Motorway Graph Builder
Full complete file — Select All (Ctrl+A) and Paste (Ctrl+V) into:
scripts/build_graph.py
===============================================================================
"""

import argparse
import csv
import json
import math
from pathlib import Path
import random
from typing import Any, Dict, List, Tuple

import networkx as nx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
GRAPH_SUBDIR = DATA_DIR / "graph"
HOSPITALS_FILE = DATA_DIR / "hospitals.json"

NODES_CSV_MAIN = DATA_DIR / "nodes.csv"
EDGES_CSV_MAIN = DATA_DIR / "edges.csv"
NODES_CSV_SUB = GRAPH_SUBDIR / "nodes.csv"
EDGES_CSV_SUB = GRAPH_SUBDIR / "edges.csv"

MANCHESTER_CENTER_LAT = 53.4808
MANCHESTER_CENTER_LON = -2.2426

ROAD_CLASS_SPECS: Dict[str, Dict[str, float]] = {
    "motorway": {"speed_kph": 96.0, "Tortuosity": 1.04},
    "trunk": {"speed_kph": 76.0, "Tortuosity": 1.06},
    "primary": {"speed_kph": 60.0, "Tortuosity": 1.08},
    "secondary": {"speed_kph": 48.0, "Tortuosity": 1.10},
    "tertiary": {"speed_kph": 38.0, "Tortuosity": 1.12},
}


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in meters between two WGS84 coordinates."""
    r_earth = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    return 2.0 * r_earth * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))


def load_hospitals() -> List[Dict[str, Any]]:
    if not HOSPITALS_FILE.exists():
        raise FileNotFoundError(f"Missing {HOSPITALS_FILE}.")
    with HOSPITALS_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def generate_manchester_graph(
    seed: int = 42,
    grid_rows: int = 36,
    grid_cols: int = 38,
) -> Tuple[nx.MultiDiGraph, List[Dict[str, Any]]]:
    """
    Build a high-resolution street-block and motorway graph across Greater Manchester
    so ambulance routes follow crisp road corridors and detour cleanly around roadblocks.
    """
    rng = random.Random(seed)
    hospitals = load_hospitals()
    G = nx.MultiDiGraph()

    # 1. Add the 8 NHS Hospital nodes (IDs 0..7)
    for idx, hosp in enumerate(hospitals):
        hosp["node_id"] = idx
        G.add_node(
            idx,
            lat=round(float(hosp["lat"]), 6),
            lon=round(float(hosp["lon"]), 6),
            is_hospital=True,
            hospital_id=hosp["id"],
            label=hosp["name"],
        )

    with HOSPITALS_FILE.open("w", encoding="utf-8") as f:
        json.dump(hospitals, f, indent=2)

    next_node_id = len(hospitals)

    # 2. Central Manchester hub (ID 8)
    center_node_id = next_node_id
    G.add_node(
        center_node_id,
        lat=MANCHESTER_CENTER_LAT,
        lon=MANCHESTER_CENTER_LON,
        is_hospital=False,
        hospital_id="",
        label="Manchester City Centre",
    )
    next_node_id += 1

    # 3. M60 Orbital Motorway Ring (48 smooth waypoints)
    m60_ring_nodes: List[int] = []
    num_ring_nodes = 48
    ring_radius_lat = 0.068
    ring_radius_lon = 0.115
    for i in range(num_ring_nodes):
        angle = (2.0 * math.pi * i) / num_ring_nodes
        lat = round(
            MANCHESTER_CENTER_LAT + ring_radius_lat * math.sin(angle) + rng.uniform(-0.0012, 0.0012),
            6,
        )
        lon = round(
            MANCHESTER_CENTER_LON + ring_radius_lon * math.cos(angle) + rng.uniform(-0.0018, 0.0018),
            6,
        )
        G.add_node(next_node_id, lat=lat, lon=lon, is_hospital=False, hospital_id="", label=f"M60_{i+1}")
        m60_ring_nodes.append(next_node_id)
        next_node_id += 1

    # 4. A57(M) Mancunian Way / Inner Ring (24 waypoints)
    inner_ring_nodes: List[int] = []
    num_inner_nodes = 24
    for i in range(num_inner_nodes):
        angle = (2.0 * math.pi * i) / num_inner_nodes
        lat = round(MANCHESTER_CENTER_LAT + 0.022 * math.sin(angle) + rng.uniform(-0.0008, 0.0008), 6)
        lon = round(MANCHESTER_CENTER_LON + 0.036 * math.cos(angle) + rng.uniform(-0.0012, 0.0012), 6)
        G.add_node(next_node_id, lat=lat, lon=lon, is_hospital=False, hospital_id="", label=f"InnerRing_{i+1}")
        inner_ring_nodes.append(next_node_id)
        next_node_id += 1

    # 5. Dense Greater Manchester Street-Block Grid (36 x 38 = 1,368 urban block intersections)
    lat_min, lat_max = 53.368, 53.568
    lon_min, lon_max = -2.375, -2.055
    d_lat = (lat_max - lat_min) / (grid_rows - 1)
    d_lon = (lon_max - lon_min) / (grid_cols - 1)

    grid_node_map: Dict[Tuple[int, int], int] = {}
    for r in range(grid_rows):
        for c in range(grid_cols):
            base_lat = lat_min + r * d_lat
            base_lon = lon_min + c * d_lon
            jitter_lat = rng.uniform(-0.18 * d_lat, 0.18 * d_lat)
            jitter_lon = rng.uniform(-0.18 * d_lon, 0.18 * d_lon)
            G.add_node(
                next_node_id,
                lat=round(base_lat + jitter_lat, 6),
                lon=round(base_lon + jitter_lon, 6),
                is_hospital=False,
                hospital_id="",
                label=f"Block_{r}_{c}",
            )
            grid_node_map[(r, c)] = next_node_id
            next_node_id += 1

    def add_bidirectional_road(u: int, v: int, road_class: str, speed_jitter: float = 1.0) -> None:
        if u == v or G.has_edge(u, v):
            return
        lat_u, lon_u = G.nodes[u]["lat"], G.nodes[u]["lon"]
        lat_v, lon_v = G.nodes[v]["lat"], G.nodes[v]["lon"]
        straight_m = haversine_m(lat_u, lon_u, lat_v, lon_v)
        spec = ROAD_CLASS_SPECS[road_class]
        length_m = round(max(35.0, straight_m * spec["Tortuosity"]), 1)
        speed_kph = round(spec["speed_kph"] * speed_jitter, 1)

        G.add_edge(
            u,
            v,
            length_m=length_m,
            speed_kph=speed_kph,
            road_class=road_class,
            geometry=f"{lat_u},{lon_u};{lat_v},{lon_v}",
        )
        G.add_edge(
            v,
            u,
            length_m=length_m,
            speed_kph=speed_kph,
            road_class=road_class,
            geometry=f"{lat_v},{lon_v};{lat_u},{lon_u}",
        )

    # Connect M60 motorway ring
    for i in range(num_ring_nodes):
        add_bidirectional_road(
            m60_ring_nodes[i],
            m60_ring_nodes[(i + 1) % num_ring_nodes],
            "motorway",
            rng.uniform(0.96, 1.04),
        )

    # Connect Inner Ring (Mancunian Way)
    for i in range(num_inner_nodes):
        add_bidirectional_road(
            inner_ring_nodes[i],
            inner_ring_nodes[(i + 1) % num_inner_nodes],
            "trunk",
            rng.uniform(0.95, 1.04),
        )

    # Connect N-S, E-W, and diagonal radial avenues across Manchester street blocks
    for r in range(grid_rows):
        for c in range(grid_cols):
            u = grid_node_map[(r, c)]
            is_arterial_row = (r % 5 == 0) or (abs(r - grid_rows // 2) <= 1)
            is_arterial_col = (c % 5 == 0) or (abs(c - grid_cols // 2) <= 1)

            if r + 1 < grid_rows:
                v_north = grid_node_map[(r + 1, c)]
                rc_ns = "primary" if is_arterial_col else ("secondary" if c % 2 == 0 else "tertiary")
                add_bidirectional_road(u, v_north, rc_ns, rng.uniform(0.92, 1.06))

            if c + 1 < grid_cols:
                v_east = grid_node_map[(r, c + 1)]
                rc_ew = "primary" if is_arterial_row else ("secondary" if r % 2 == 0 else "tertiary")
                add_bidirectional_road(u, v_east, rc_ew, rng.uniform(0.92, 1.06))

            if r + 1 < grid_rows and c + 1 < grid_cols and ((r + c) % 4 == 0):
                v_diag = grid_node_map[(r + 1, c + 1)]
                add_bidirectional_road(u, v_diag, "secondary", rng.uniform(0.94, 1.04))
            if r + 1 < grid_rows and c - 1 >= 0 and ((r - c) % 4 == 0):
                v_diag2 = grid_node_map[(r + 1, c - 1)]
                add_bidirectional_road(u, v_diag2, "secondary", rng.uniform(0.94, 1.04))

    # Connect hospitals, M60 junctions, and Inner Ring junctions smoothly into the street block grid
    all_node_ids = list(G.nodes())
    coords = {nid: (G.nodes[nid]["lat"], G.nodes[nid]["lon"]) for nid in all_node_ids}
    special_nodes = list(range(len(hospitals) + 1)) + m60_ring_nodes + inner_ring_nodes

    for u in special_nodes:
        lat_u, lon_u = coords[u]
        nearest = sorted(
            ((haversine_m(lat_u, lon_u, coords[v][0], coords[v][1]), v) for v in all_node_ids if v != u),
            key=lambda x: x[0],
        )
        k_links = 6 if G.nodes[u].get("is_hospital") else 4
        for idx_n, (_, v) in enumerate(nearest[:k_links]):
            r_class = "primary" if idx_n < 3 else "secondary"
            add_bidirectional_road(u, v, r_class, rng.uniform(0.95, 1.05))

    return G, hospitals


def export_graph_to_csv(G: nx.MultiDiGraph) -> Tuple[int, int]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    GRAPH_SUBDIR.mkdir(parents=True, exist_ok=True)

    node_rows = [
        {
            "id": nid,
            "lat": G.nodes[nid]["lat"],
            "lon": G.nodes[nid]["lon"],
            "is_hospital": int(bool(G.nodes[nid].get("is_hospital", False))),
            "hospital_id": G.nodes[nid].get("hospital_id", ""),
        }
        for nid in sorted(G.nodes())
    ]

    edge_rows = [
        {
            "u": u,
            "v": v,
            "length_m": edata["length_m"],
            "speed_kph": edata["speed_kph"],
            "road_class": edata["road_class"],
            "geometry": edata["geometry"],
        }
        for u, v, edata in G.edges(data=True)
    ]

    for target_nodes_csv in (NODES_CSV_MAIN, NODES_CSV_SUB):
        with target_nodes_csv.open("w", newline="", encoding="utf-8") as f_n:
            writer = csv.DictWriter(f_n, fieldnames=["id", "lat", "lon", "is_hospital", "hospital_id"])
            writer.writeheader()
            writer.writerows(node_rows)

    for target_edges_csv in (EDGES_CSV_MAIN, EDGES_CSV_SUB):
        with target_edges_csv.open("w", newline="", encoding="utf-8") as f_e:
            writer = csv.DictWriter(
                f_e, fieldnames=["u", "v", "length_m", "speed_kph", "road_class", "geometry"]
            )
            writer.writeheader()
            writer.writerows(edge_rows)

    return len(node_rows), len(edge_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate high-density Greater Manchester road network.")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    G, hospitals = generate_manchester_graph(seed=args.seed)
    n_nodes, n_edges = export_graph_to_csv(G)
    is_connected = nx.is_strongly_connected(G)

    print("=" * 72)
    print("TRIAGE — High-Density Manchester Street & Motorway Graph Complete!")
    print("=" * 72)
    print(f"Hospitals linked     : {len(hospitals)} (Node IDs 0..{len(hospitals)-1})")
    print(f"Total street nodes   : {n_nodes} -> {NODES_CSV_MAIN}")
    print(f"Total directed edges : {n_edges} -> {EDGES_CSV_MAIN}")
    print(f"Strongly connected   : {is_connected}")
    print("=" * 72)


if __name__ == "__main__":
    main()