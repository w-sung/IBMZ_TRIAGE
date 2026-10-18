# TRIAGE - Development Log & AI Handoff
**Branches:** `arno-dev-branch` (chunk 1), `tom-dev-branch` (chunk 2)
**Current Phase:** Chunk 3 implementation prepared; integration against the latest repo branch pending.

## Status by chunk
| Chunk | Status |
|---|---|
| 1. Foundation and synthetic data | Done |
| 2. Manchester map, hospitals, routing, time-of-day traffic | **Done.** Real OSM graph built (10,204 nodes, 21,008 edges) and all 8 hospitals resolved. Still to do: check hospital pins on a map, re-measure the 100 ms routing budget on the real graph. |
| 3. Predictive AI deterioration model | Implementation prepared; isolated tests pass, repo integration pending |
| 4 to 7 | Not started |

## Changelog (latest first)
**2026-10-18, chunk 3 implementation prepared — integration pending**
- Added `backend/app/health/scoring.py`: deterministic, NEWS2-inspired synthetic label function, bounded severity score, risk-feature builder, condition priors and diagnostic-only expected-S0 bands. This is not a full NEWS2 implementation or clinical validation.
- Added `backend/app/health/patients.py`: tolerant JSON loading for list- or mapping-based `patients.json` / `conditions.json`, plus seeded, condition-stratified synthetic augmentation (default 5,000 rows).
- Added `backend/app/health/model.py`: `HistGradientBoostingRegressor`, fixed seed, held-out MAE/R² diagnostics, bounded `SeverityPredictor.predict(patient)`, and in-memory `get_default_model()`. No `.pkl` / `.joblib` is produced or committed; model trains locally on the target platform.
- Added `backend/app/health/deterioration.py`: deterministic condition base-rate lookup, shock-index/SpO2 and age multipliers, `deterioration_at()` cap at 100, and Category 1–4 mapping.
- Added `backend/app/health/train.py`: `python -m backend.app.health.train` trains the model and prints training time, synthetic-label validation metrics, and condition-band diagnostics.
- Added `backend/tests/test_health.py`: 11 health tests covering score bounds and monotonicity, condition-prior ordering, deterministic training data, model monotonicity/range, expected-band diagnostics on neutral test records, rate calculations and category thresholds.
- Isolated patch verification: `python -m pytest backend/tests/test_health.py -q` → **11 passed**; Python compile check passed. A 5,000-row CLI smoke test on synthetic fixture JSON passed (validation metrics measure agreement with our synthetic label function only, not clinical performance).
- **No Chunk 1 or Chunk 2 source files were changed** in this implementation. `main.py`, routing, traffic, graph/hospital data, `scripts/make_patients.py`, and dependency manifests remain untouched to avoid changing working contracts.
- **Integration is still pending:** apply this patch on a fresh feature branch, run `python -m pytest backend/tests -q` against the actual repo, then run the training CLI against its real synthetic JSON files. Chunk 4 should wire `get_default_model().predict(patient)`, `calculate_deterioration_rate(patient, conditions)`, and `severity_category(score)` into its simulation without placing training/network calls inside each simulation tick.

**2026-10-17, chunk 2 finished**
- Ran `scripts/build_graph.py` for real: `data/graph/nodes.csv` and `edges.csv` now exist, and `data/hospitals.json` has `lat`, `lon`, `node_id` filled for all 8 hospitals.
- First run crashed with `ImportError: scikit-learn must be installed ... to search an unprojected graph`. Fix: `pip install scikit-learn` (build step only).
- `main.py` wired to chunk 2: new `/api/hospitals`, `/api/traffic`, `/api/route`, and routing status in `/api/health`.
- Roadblock bug found by a test and fixed: distance was measured to a road's midpoint, so blocks on junctions missed long roads. It now uses distance to the whole segment.
- Folder `Scripts/` renamed to `scripts/` (Linux and Docker are case-sensitive).
- `.gitignore` now excludes `cache/` (osmnx download cache) and `.venv/`.
- Tests: 11 passing (6 routing, 5 API).

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
pip install osmnx scikit-learn numpy scipy fastapi uvicorn httpx pytest   # inside a venv; osmnx is x86/Mac only
python scripts/build_graph.py              # once. Check each hospital's printed lat/lon on a map.
uvicorn backend.app.main:app --port 8000   # then open /api/health: routing.ready true, graph_source "graph"
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

**`main.py` changes (v0.2.0)**
- Added a startup `lifespan` that loads the graph, hospitals, `TravelEngine` and `TrafficModel` once. If data is missing it does **not** crash: `/api/health` reports why (`routing.reason`) and the new endpoints return 503.
- Graph location: `GRAPH_DIR` env, else `data/graph`, else falls back to `data/graph_dev` (synthetic). `/api/health` shows `routing.graph_source`; if it says `graph_dev`, the data is not real. Other env vars: `HOSPITALS_PATH`, `DEFAULT_SEED` (traffic noise, default 42).
- `/api/health` now also reports `hospitals_json`, `routing`, node and hospital counts. Chunk 1 fields are unchanged.
- New endpoints (all GET):
  - `/api/hospitals?hour=` hospitals with `beds_free` and `effective_wait_min` (base wait times time-of-day pressure).
  - `/api/traffic?level=&hour=` mean and min speed multiplier for the slider and clock.
  - `/api/route?hospital_id=&lat=&lon=&level=&hour=` ETA in seconds and the road route as `[lat, lon]` points.
- Handlers are `async def` with no awaits on purpose: `TravelEngine` keeps its last result in memory, so they must not run in a threadpool at the same time. Chunk 4 should keep this in mind (give the sim its own engine).
- `backend/tests/test_api.py`: 5 tests (health, hospitals, traffic, route and errors, 503 when data missing). Full suite: 11 passing.

**Real build results (from `build_graph.py`)**
| id | lat | lon |
|---|---|---|
| mri | 53.46292 | -2.22610 |
| wyth | 53.39063 | -2.29093 |
| salf | 53.48748 | -2.32434 |
| nmgh | 53.51746 | -2.22875 |
| oldh | 53.55207 | -2.12388 |
| step | 53.38453 | -2.13341 |
| tame | 53.49322 | -2.06998 |
| traf | 53.45382 | -2.37065 |

Geocoded by OSM Nominatim and snapped to the nearest road node. Not yet checked by eye on a map.

**Repo hygiene**
- **Commit:** `data/graph/nodes.csv`, `data/graph/edges.csv`, `data/hospitals.json`. LinuxONE cannot run `build_graph.py`, so it reads these files, and every teammate then routes on the same map.
- **Never commit:** `cache/`, `.venv/`, `.env`. Use explicit paths with `git add`, not `git add .`.
- There is a separate `TRIAGE_App/` folder with its own `backend` and `frontend`. Check whether it is a duplicate before committing.

**Known limits and assumptions**
- All traffic and hospital-pressure numbers are tunable guesses, not measurements. Say so in the README.
- Hospital beds, waits and specialties are illustrative, not facts about those hospitals.
- Roadblock distance uses the straight line between a road's endpoints, so sharply curved roads are approximate.
- The 100 ms travel-time budget was only measured on the 900-node dev graph. **Still to re-measure on the real 10,204-node graph.**
