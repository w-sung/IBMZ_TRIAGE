"""
TRIAGE — Greater Manchester Synthetic Road Network Generator (Chunk 2)

Builds a realistic, strongly-connected road network across Greater Manchester
connecting all 8 NHS hospitals from data/hospitals.json without requiring OSMnx
or GDAL/Geopandas C-extensions.

Outputs:
  - data/nodes.csv (and data/graph/nodes.csv)
  - data/edges.csv (and data/graph/edges.csv) with length_m and speed_kph
"""

import argparse
import csv
import json
import math
from pathlib import Path
import random
from typing import Any, Dict, List, Tuple

import networkx as nx

# Resolve project root and data directories
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
GRAPH_SUBDIR = DATA_DIR / "graph"
HOSPITALS_FILE = DATA_DIR / "hospitals.json"

NODES_CSV_MAIN = DATA_DIR / "nodes.csv"
EDGES_CSV_MAIN = DATA_DIR / "edges.csv"
NODES_CSV_SUB = GRAPH_SUBDIR / "nodes.csv"
EDGES_CSV_SUB = GRAPH_SUBDIR / "edges.csv"

# Greater Manchester centre (St Peter's Square / Piccadilly)
MANCHESTER_CENTER_LAT = 53.4808
MANCHESTER_CENTER_LON = -2.2426

# Road class speed profiles (km/h) and curvature multipliers
ROAD_CLASS_SPECS: Dict[str, Dict[str, float]] = {
    "motorway": {"speed_kph": 96.0, "Tortuosity": 1.08},
    "trunk": {"speed_kph": 76.0, "Tortuosity": 1.12},
    "primary": {"speed_kph": 60.0, "Tortuosity": 1.16},
    "secondary": {"speed_kph": 48.0, "Tortuosity": 1.20},
    "tertiary": {"speed_kph": 36.0, "Tortuosity": 1.25},
}


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate great-circle distance in meters between two WGS84 coordinates.
    """
    r_earth = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return r_earth * c


def load_hospitals() -> List[Dict[str, Any]]:
    """Load the 8 Manchester hospitals from data/hospitals.json."""
    if not HOSPITALS_FILE.exists():
        raise FileNotFoundError(
            f"Missing {HOSPITALS_FILE}. Please create data/hospitals.json first."
        )
    with HOSPITALS_FILE.open("r", encoding="utf-8") as f:
        hospitals = json.load(f)
    return hospitals


def generate_manchester_graph(
    seed: int = 42,
    num_random_nodes: int = 380,
) -> Tuple[nx.MultiDiGraph, List[Dict[str, Any]]]:
    """
    Build a directed multi-graph (nx.MultiDiGraph) representing Greater Manchester:
      - Nodes 0..7: The 8 Manchester hospitals at their exact coordinates
      - Node 8: Manchester City Centre hub
      - Nodes 9..32: M60 Orbital Motorway ring junctions around Manchester
      - Nodes 33..N: Radial arterial junctions and suburban road intersections
    """
    rng = random.Random(seed)
    hospitals = load_hospitals()
    G = nx.MultiDiGraph()

    # 1. Add the 8 hospital nodes first (node_id 0..7)
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

    # Save updated node_ids back to hospitals.json to guarantee synchronization
    with HOSPITALS_FILE.open("w", encoding="utf-8") as f:
        json.dump(hospitals, f, indent=2)

    next_node_id = len(hospitals)

    # 2. Add central Manchester hub node (id = 8)
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

    # 3. Generate M60 Orbital Motorway Ring (24 junctions around Manchester)
    m60_ring_nodes: List[int] = []
    num_ring_nodes = 24
    ring_radius_lat = 0.068  # ~7.5 km N-S radius
    ring_radius_lon = 0.115  # ~7.5 km E-W radius
    for i in range(num_ring_nodes):
        angle = (2.0 * math.pi * i) / num_ring_nodes
        jitter_lat = rng.uniform(-0.003, 0.003)
        jitter_lon = rng.uniform(-0.004, 0.004)
        lat = round(MANCHESTER_CENTER_LAT + ring_radius_lat * math.sin(angle) + jitter_lat, 6)
        lon = round(MANCHESTER_CENTER_LON + ring_radius_lon * math.cos(angle) + jitter_lon, 6)
        G.add_node(
            next_node_id,
            lat=lat,
            lon=lon,
            is_hospital=False,
            hospital_id="",
            label=f"M60_J{i+1}",
        )
        m60_ring_nodes.append(next_node_id)
        next_node_id += 1

    # 4. Generate inner ring road (Mancunian Way / A57(M) - 12 junctions)
    inner_ring_nodes: List[int] = []
    num_inner_nodes = 12
    for i in range(num_inner_nodes):
        angle = (2.0 * math.pi * i) / num_inner_nodes
        lat = round(MANCHESTER_CENTER_LAT + 0.024 * math.sin(angle) + rng.uniform(-0.002, 0.002), 6)
        lon = round(MANCHESTER_CENTER_LON + 0.040 * math.cos(angle) + rng.uniform(-0.002, 0.002), 6)
        G.add_node(
            next_node_id,
            lat=lat,
            lon=lon,
            is_hospital=False,
            hospital_id="",
            label=f"Inner_Ring_{i+1}",
        )
        inner_ring_nodes.append(next_node_id)
        next_node_id += 1

    # 5. Generate suburban & arterial road nodes across Greater Manchester bounding box
    # Bounding box spans Trafford/Salford in the West to Tameside/Oldham in the East,
    # and Wythenshawe/Stepping Hill in the South to North Manchester/Oldham in the North.
    lat_min, lat_max = 53.365, 53.570
    lon_min, lon_max = -2.380, -2.055

    for _ in range(num_random_nodes):
        # Mix uniform spatial coverage with radial density around Manchester centre
        if rng.random() < 0.65:
            lat = rng.uniform(lat_min, lat_max)
            lon = rng.uniform(lon_min, lon_max)
        else:
            lat = rng.gauss(MANCHESTER_CENTER_LAT, 0.048)
            lon = rng.gauss(MANCHESTER_CENTER_LON, 0.075)
            lat = max(lat_min, min(lat_max, lat))
            lon = max(lon_min, min(lon_max, lon))

        G.add_node(
            next_node_id,
            lat=round(lat, 6),
            lon=round(lon, 6),
            is_hospital=False,
            hospital_id="",
            label=f"Node_{next_node_id}",
        )
        next_node_id += 1

    def add_bidirectional_road(u: int, v: int, road_class: str, speed_jitter: float = 1.0) -> None:
        if u == v:
            return
        lat_u, lon_u = G.nodes[u]["lat"], G.nodes[u]["lon"]
        lat_v, lon_v = G.nodes[v]["lat"], G.nodes[v]["lon"]
        straight_m = haversine_m(lat_u, lon_u, lat_v, lon_v)
        spec = ROAD_CLASS_SPECS[road_class]
        length_m = round(max(50.0, straight_m * spec["Tortuosity"]), 1)
        speed_kph = round(spec["speed_kph"] * speed_jitter, 1)
        geom_forward = f"{lat_u},{lon_u};{lat_v},{lon_v}"
        geom_reverse = f"{lat_v},{lon_v};{lat_u},{lon_u}"

        G.add_edge(
            u,
            v,
            length_m=length_m,
            speed_kph=speed_kph,
            road_class=road_class,
            geometry=geom_forward,
        )
        G.add_edge(
            v,
            u,
            length_m=length_m,
            speed_kph=speed_kph,
            road_class=road_class,
            geometry=geom_reverse,
        )

    # Connect M60 motorway ring sequentially
    for i in range(num_ring_nodes):
        u = m60_ring_nodes[i]
        v = m60_ring_nodes[(i + 1) % num_ring_nodes]
        add_bidirectional_road(u, v, "motorway", rng.uniform(0.95, 1.05))

    # Connect Inner Ring sequentially as trunk roads
    for i in range(num_inner_nodes):
        u = inner_ring_nodes[i]
        v = inner_ring_nodes[(i + 1) % num_inner_nodes]
        add_bidirectional_road(u, v, "trunk", rng.uniform(0.95, 1.05))

    # Connect Inner Ring to City Centre and M60 Ring via primary radial A-roads
    for i, inner_u in enumerate(inner_ring_nodes):
        add_bidirectional_road(center_node_id, inner_u, "primary", rng.uniform(0.92, 1.04))
        outer_v = m60_ring_nodes[(i * 2) % num_ring_nodes]
        add_bidirectional_road(inner_u, outer_v, "primary", rng.uniform(0.94, 1.05))

    # Connect every node to its k-nearest spatial neighbors so ambulances have
    # smooth, realistic multi-hop road paths across all of Greater Manchester
    all_node_ids = list(G.nodes())
    coords = {nid: (G.nodes[nid]["lat"], G.nodes[nid]["lon"]) for nid in all_node_ids}

    for u in all_node_ids:
        lat_u, lon_u = coords[u]
        distances: List[Tuple[float, int]] = []
        for v in all_node_ids:
            if u == v:
                continue
            lat_v, lon_v = coords[v]
            d = haversine_m(lat_u, lon_u, lat_v, lon_v)
            distances.append((d, v))
        distances.sort(key=lambda item: item[0])

        # Hospital nodes get extra primary/secondary access links
        k_neighbors = 6 if G.nodes[u].get("is_hospital") else 4
        for idx_n, (dist_m, v) in enumerate(distances[:k_neighbors]):
            if G.has_edge(u, v):
                continue
            if G.nodes[u].get("is_hospital") or G.nodes[v].get("is_hospital"):
                r_class = "primary" if idx_n < 2 else "secondary"
            elif dist_m > 2800:
                r_class = "primary"
            elif dist_m > 1500:
                r_class = "secondary"
            else:
                r_class = "tertiary"
            add_bidirectional_road(u, v, r_class, rng.uniform(0.90, 1.08))

    # Inject a few parallel edges (e.g., fast A-road + slower local service road)
    # between identical node pairs so routing/graph.py can demonstrate parallel edge deduplication
    for i in range(5):
        u = m60_ring_nodes[i]
        v = m60_ring_nodes[(i + 1) % num_ring_nodes]
        add_bidirectional_road(u, v, "tertiary", 0.75)

    return G, hospitals


def export_graph_to_csv(G: nx.MultiDiGraph) -> Tuple[int, int]:
    """
    Write nodes.csv and edges.csv to both data/ and data/graph/ for full compatibility.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    GRAPH_SUBDIR.mkdir(parents=True, exist_ok=True)

    node_rows: List[Dict[str, Any]] = []
    for nid in sorted(G.nodes()):
        ndata = G.nodes[nid]
        node_rows.append(
            {
                "id": nid,
                "lat": ndata["lat"],
                "lon": ndata["lon"],
                "is_hospital": int(bool(ndata.get("is_hospital", False))),
                "hospital_id": ndata.get("hospital_id", ""),
            }
        )

    edge_rows: List[Dict[str, Any]] = []
    for u, v, edata in G.edges(data=True):
        edge_rows.append(
            {
                "u": u,
                "v": v,
                "length_m": edata["length_m"],
                "speed_kph": edata["speed_kph"],
                "road_class": edata["road_class"],
                "geometry": edata["geometry"],
            }
        )

    for target_nodes_csv in (NODES_CSV_MAIN, NODES_CSV_SUB):
        with target_nodes_csv.open("w", newline="", encoding="utf-8") as f_n:
            writer = csv.DictWriter(
                f_n, fieldnames=["id", "lat", "lon", "is_hospital", "hospital_id"]
            )
            writer.writeheader()
            writer.writerows(node_rows)

    for target_edges_csv in (EDGES_CSV_MAIN, EDGES_CSV_SUB):
        with target_edges_csv.open("w", newline="", encoding="utf-8") as f_e:
            writer = csv.DictWriter(
                f_e,
                fieldnames=["u", "v", "length_m", "speed_kph", "road_class", "geometry"],
            )
            writer.writeheader()
            writer.writerows(edge_rows)

    return len(node_rows), len(edge_rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate synthetic Greater Manchester road network (nodes.csv & edges.csv)."
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument(
        "--nodes",
        type=int,
        default=380,
        help="Number of suburban/arterial intersection nodes (default: 380)",
    )
    args = parser.parse_args()

    G, hospitals = generate_manchester_graph(seed=args.seed, num_random_nodes=args.nodes)
    n_nodes, n_edges = export_graph_to_csv(G)

    # Verify strong connectivity
    is_connected = nx.is_strongly_connected(G)

    print("=" * 72)
    print("TRIAGE — Greater Manchester Road Graph Builder Complete!")
    print("=" * 72)
    print(f"Hospitals linked     : {len(hospitals)} (Node IDs 0..{len(hospitals)-1})")
    print(f"Total road nodes     : {n_nodes} -> {NODES_CSV_MAIN}")
    print(f"Total directed edges : {n_edges} -> {EDGES_CSV_MAIN}")
    print(f"Strongly connected   : {is_connected}")
    print("-" * 72)
    print("Hospital Node Mapping:")
    for h in hospitals:
        print(
            f"  [Node {h['node_id']:>2}] {h['id']:<10} | {h['name']:<34} "
            f"({h['lat']:.4f}, {h['lon']:.4f})"
        )
    print("=" * 72)


if __name__ == "__main__":
    main()