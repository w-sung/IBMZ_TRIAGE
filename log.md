# TRIAGE - Development Log & AI Handoff
**Branch:** `arno-dev-branch` (chunk 1), chunk 2 files are new and listed below
**Current Phase:** Chunk 2 code complete (routing, traffic, hospitals). Chunk 3 next.

## Status by chunk
| Chunk | Status |
|---|---|
| 1. Foundation and synthetic data | Done |
| 2. Manchester map, hospitals, routing, time-of-day traffic | Code done and tested on a synthetic dev graph. **Real OSM graph and hospital coordinates still need `scripts/build_graph.py` run in WSL.** |
| 3 to 7 | Not started |

## 1. Chunk 1: what was built (Arno)
- **FastAPI skeleton:** `backend/app/main.py` with CORS and `/api/health`, which checks architecture (ready for s390x) and that data files exist.
- **Synthetic patient generator:** `scripts/make_patients.py`, deterministic, 20 conditions from `CONTEXT.md`.

**Run it:**
```bash
python scripts/make_patients.py            # optional: --seed 42 --count 100
```
- Inputs: optional `--seed` (default 42) and `--count` (default 100).
- Outputs: `data/conditions.json` (20 conditions with profiles) and `data/patients.json`.

**Patient schema (use these exact names):**
```json
{
  "patient_id": "p_001", "age": 68, "sex": "F", "condition_id": "stemi",
  "vitals": {"hr": 0, "sbp": 0, "rr": 0, "spo2": 0, "etco2": 0, "spco": 0.0,
             "methb": 0.0, "ecg_rhythm": "str", "st_elevation": false, "consciousness": "str"}
}
```
`main.py` already defines `app`, `PROJECT_ROOT`, `DATA_DIR`, `CONDITIONS_PATH`, `PATIENTS_PATH`. Reuse them.

## 2. Chunk 2: what changed
**New files**
| File | Purpose |
|---|---|
| `backend/app/routing/graph.py` | Loads `nodes.csv` / `edges.csv` into a `RoadGraph`. Dedupes parallel roads to the **minimum** travel time (scipy would otherwise sum them). CSV only, no pickle. |
| `backend/app/routing/travel.py` | `TravelEngine`: `travel_times(multiplier)` returns a hospital-by-node matrix in seconds (one backwards Dijkstra per hospital). `path()` and `path_latlon()` rebuild routes. `load_hospitals()` joins `hospitals.json` to graph nodes. |
| `backend/app/sim/traffic.py` | `TrafficModel.multiplier(level, hour, roadblocks)` gives a per-edge speed multiplier. `time_of_day_curve(hour)` and `hospital_pressure(hour)` give the dynamic-time feature. |
| `data/hospitals.json` | 8 candidate hospitals with illustrative beds, waits, specialties. `lat`, `lon`, `node_id` are `null` until the build script fills them. |
| `scripts/build_graph.py` | **WSL only.** Downloads the OSM road graph, writes `data/graph/*.csv`, geocodes each hospital and writes `lat/lon/node_id` into `hospitals.json`. **Not tested** (the build sandbox cannot reach OSM). |
| `scripts/make_dev_graph.py` | Synthetic 30x30 road grid in `data/graph_dev/` for development and tests. Not for the demo. |
| `backend/tests/test_routing.py` | 6 tests, all passing: parallel-edge dedupe, backwards search equals forward search, path cost equals travel time, traffic ranges and determinism, roadblocks, 100 ms budget. |

**How to run**
```bash
python scripts/build_graph.py              # WSL, once. Check each hospital's printed lat/lon on a map.
python -m pytest backend/tests -q          # from repo root
```
```python
from backend.app.routing.graph import load_graph
from backend.app.routing.travel import TravelEngine, load_hospitals
from backend.app.sim.traffic import TrafficModel, hospital_pressure
g = load_graph("data/graph")               # or "data/graph_dev"
hosp = load_hospitals("data/hospitals.json", g)
eng = TravelEngine(g, [h["node_idx"] for h in hosp])
m = TrafficModel(g, seed=42).multiplier(level=0.8, hour=8.5, roadblocks=[(53.47, -2.24, 300)])
times = eng.travel_times(m)                # times[h, node] in seconds
route = eng.path_latlon(h=0, node=g.nearest_node(53.50, -2.30))
wait_min = hosp[0]["base_wait_min"] * hospital_pressure(8.5)
```

**Contracts for other chunks (do not change without telling the owner)**
- Node values are **indices** into the graph arrays, not OSM ids. `graph.index_of(osm_id)` converts.
- Traffic: `level` is 0 to 1 (`LEVELS`: off_peak 0.3, normal 0.6, rush_hour 1.0). `hour=None` means the slider alone drives traffic; a number scales it by the clock curve. Roadblocks are `(lat, lon, radius_m)` and force multiplier 0.02. Ambulances feel half the slowdown.
- `hospital_pressure(hour)` is a multiplier (0.75 to 1.5) for chunk 4 to apply to `base_wait_min`.

**Known limits and assumptions**
- All traffic and hospital-pressure numbers are tunable guesses, not measurements. Say so in the README.
- Hospital beds, waits and specialties are illustrative, not facts about those hospitals.
- Roadblock distance uses the straight line between a road's endpoints, so sharply curved roads are approximate.
- The 100 ms travel-time budget was only measured on the 900-node dev graph. Re-measure on the real graph (expect 10 to 20 thousand nodes).
- `main.py` is not wired up yet: no `/api/hospitals` or traffic endpoint exists.
