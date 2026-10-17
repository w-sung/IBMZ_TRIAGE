"""Synthetic road grid so routing can be built and tested without OSM. Not for the demo."""
import csv
import sys
from pathlib import Path

LAT0, LON0, DLAT, DLON = 53.40, -2.35, 0.0072, 0.012  # roughly 0.8 km spacing


def make_dev_graph(out_dir, n: int = 30) -> Path:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    node = lambda r, c: 1000 + r * n + c  # OSM-style ids, deliberately not equal to indices
    with open(out / "nodes.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["id", "lat", "lon"])
        for r in range(n):
            for c in range(n):
                w.writerow([node(r, c), LAT0 + r * DLAT, LON0 + c * DLON])
    with open(out / "edges.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["u", "v", "length_m", "speed_kph", "road_class", "geometry"])
        for r in range(n):
            for c in range(n):
                for dr, dc in ((0, 1), (1, 0)):
                    r2, c2 = r + dr, c + dc
                    if r2 >= n or c2 >= n:
                        continue
                    main = (r % 5 == 0) if dr == 0 else (c % 5 == 0)
                    cls, kph = ("primary", 50) if main else ("tertiary", 30)
                    length = 800 if dr == 0 else 800
                    for a, b in ((node(r, c), node(r2, c2)), (node(r2, c2), node(r, c))):
                        w.writerow([a, b, length, kph, cls, ""])
                    if (r + c) % 7 == 0:  # parallel slower road, to exercise the dedupe
                        w.writerow([node(r, c), node(r2, c2), length * 2, 20, "unclassified", ""])
    return out


if __name__ == "__main__":
    print(make_dev_graph(sys.argv[1] if len(sys.argv) > 1 else "data/graph_dev"))
