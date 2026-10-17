"""WSL / x86 ONLY (needs osmnx). Never run on LinuxONE.
Writes data/graph/nodes.csv + edges.csv and fills lat/lon/node_id in data/hospitals.json.
Usage: python scripts/build_graph.py [--dist 13000]
Data (c) OpenStreetMap contributors, ODbL."""
import argparse
import csv
import json
import math
import time
from pathlib import Path

import osmnx as ox

ROOT = Path(__file__).resolve().parents[1]
CENTRE = (53.4808, -2.2426)  # CONTEXT.md 5.2
FILTER = '["highway"~"motorway|trunk|primary|secondary|tertiary|unclassified"]'


def haversine_m(a, b, c, d):
    p = math.pi / 180
    h = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 12742000 * math.asin(math.sqrt(h))


def main(dist: int) -> None:
    G = ox.graph_from_point(CENTRE, dist=dist, network_type="drive", custom_filter=FILTER)
    G = ox.add_edge_speeds(G)
    out = ROOT / "data" / "graph"; out.mkdir(parents=True, exist_ok=True)
    with open(out / "nodes.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["id", "lat", "lon"])
        for n, d in G.nodes(data=True):
            w.writerow([n, d["y"], d["x"]])
    with open(out / "edges.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["u", "v", "length_m", "speed_kph", "road_class", "geometry"])
        for u, v, d in G.edges(data=True):
            hw = d["highway"][0] if isinstance(d["highway"], list) else d["highway"]
            geom = ";".join(f"{y},{x}" for x, y in d["geometry"].coords) if "geometry" in d else ""
            w.writerow([u, v, d["length"], d["speed_kph"], hw.replace("_link", ""), geom])
    print(f"graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges (loader dedupes parallel edges)")

    hp = ROOT / "data" / "hospitals.json"
    data = json.loads(hp.read_text())
    for h in data["hospitals"]:
        try:
            lat, lon = ox.geocode(h["osm_query"])
        except Exception as e:  # not found by Nominatim
            print(f"WARN {h['id']}: geocode failed ({e}); left unresolved")
            continue
        finally:
            time.sleep(1.1)  # Nominatim: max 1 request per second
        if haversine_m(*CENTRE, lat, lon) > dist:
            print(f"DROP {h['id']}: outside the {dist} m map area"); h.update(lat=None, lon=None, node_id=None)
            continue
        h.update(lat=lat, lon=lon, node_id=int(ox.distance.nearest_nodes(G, lon, lat)))
        print(f"OK   {h['id']}: {lat:.5f}, {lon:.5f} (check it on the map)")
    hp.write_text(json.dumps(data, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--dist", type=int, default=13000)
    main(ap.parse_args().dist)
