import csv
import time

import numpy as np
from scipy.sparse.csgraph import dijkstra

from backend.app.routing.graph import load_graph
from backend.app.routing.travel import TravelEngine
from backend.app.sim.traffic import TrafficModel, hospital_pressure, time_of_day_curve
from scripts.make_dev_graph import make_dev_graph

HOSP = [0, 29, 435, 870, 899]


def _graph(tmp_path):
    return load_graph(make_dev_graph(tmp_path))


def test_parallel_edges_keep_minimum_not_sum(tmp_path):
    with open(tmp_path / "nodes.csv", "w", newline="") as f:
        csv.writer(f).writerows([["id", "lat", "lon"], [7, 53.4, -2.2], [9, 53.41, -2.2]])
    with open(tmp_path / "edges.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["u", "v", "length_m", "speed_kph", "road_class", "geometry"])
        w.writerow([7, 9, 30, 36, "primary", ""])  # 3 s
        w.writerow([7, 9, 50, 36, "primary", ""])  # 5 s
    g = load_graph(tmp_path)
    assert g.csr(g.base_s)[0, 1] == 3.0


def test_backward_search_matches_forward(tmp_path):
    g = _graph(tmp_path)
    eng = TravelEngine(g, HOSP)
    times = eng.travel_times()
    fwd = g.csr(g.base_s)
    for node in (5, 123, 600, 777):
        d = dijkstra(fwd, directed=True, indices=node)
        for h, hn in enumerate(HOSP):
            assert np.isclose(times[h, node], d[hn])


def test_path_reconstruction_sums_to_travel_time(tmp_path):
    g = _graph(tmp_path)
    eng = TravelEngine(g, HOSP)
    eng.travel_times(TrafficModel(g, 1).multiplier(0.8, hour=8.5))
    for node, h in ((100, 2), (650, 0), (333, 4)):
        p = eng.path(h, node)
        assert p[0] == node and p[-1] == HOSP[h]
        total = sum(eng.weights[eng._edge_of[(a, b)]] for a, b in zip(p, p[1:]))
        assert np.isclose(total, eng.times[h, node])
        assert len(eng.path_latlon(h, node)) >= len(p)


def test_traffic_ranges_and_time_of_day(tmp_path):
    g = _graph(tmp_path)
    tm = TrafficModel(g, 7)
    rush, night = tm.multiplier(1.0, 8.5), tm.multiplier(1.0, 3.0)
    assert rush.mean() < night.mean()
    assert 0.15 <= rush.min() and rush.max() <= 1.0
    assert time_of_day_curve(8.5) > time_of_day_curve(3.0)
    assert hospital_pressure(8.5) > hospital_pressure(3.0)
    assert (tm.multiplier(0.0, 8.5) == 1.0).all()
    assert (tm.multiplier(1.0, 8.5) == TrafficModel(g, 7).multiplier(1.0, 8.5)).all()  # deterministic


def test_roadblock_and_congestion_slow_routes(tmp_path):
    g = _graph(tmp_path)
    tm = TrafficModel(g, 3)
    lat, lon = float(g.lat[435]), float(g.lon[435])
    m = tm.multiplier(0.5, None, [(lat, lon, 300.0)])
    near = tm.distance_to(lat, lon) <= 300
    assert near.any() and (m[near] == 0.02).all() and (m[~near] > 0.15).all()
    eng = TravelEngine(g, HOSP)
    free = eng.travel_times().copy()
    assert (eng.travel_times(m) >= free - 1e-9).all()


def test_travel_times_under_100ms(tmp_path):
    g = _graph(tmp_path)
    eng, m = TravelEngine(g, HOSP + [10, 20, 30]), TrafficModel(g, 1).multiplier(0.6, 12)
    eng.travel_times(m)
    t0 = time.perf_counter(); eng.travel_times(m)
    assert time.perf_counter() - t0 < 0.1  # dev graph only; re-measure on the real OSM graph
