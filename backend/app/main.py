"""
TRIAGE — FastAPI Backend Server & 5Hz WebSocket Simulation Stream (Chunk 6)

Implements CONTEXT.md Section 6.6, Section 7, and Section 8:
  - Serves the static frontend (`frontend/index.html`, `/css`, `/js`) at `/`.
  - Initializes the CSR `RoutingGraph`, `Predictor` (HistGradientBoostingRegressor),
    and `NoteGenerator` (DeepSeek via OpenRouter with template fallback).
  - `POST /api/start`: Spawns N ambulances (e.g., 5 or 10) on the Greater Manchester
    road graph, predicts each patient's S0 severity and deterioration rate, computes
    real road polylines via backwards Dijkstra, and initializes `SimulationEngine`.
  - `GET /api/impact`: Returns the 44,000 Annual Severe Harm Impact Calculator summary,
    including a direct head-to-head comparison against the `NEAREST` baseline on the
    exact same seed.
  - `PATCH /api/hospital/{hospital_id}`: Live-edits hospital beds or wait time.
  - `POST /api/roadblock`: Places a live roadblock on the map and triggers an immediate replan.
  - `WebSocket /ws`: Streams `engine.tick()` states at 5Hz (0.2s wall-clock interval)
    with configurable simulation speed multiplier, plus async DeepSeek note upgrades.
"""

from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import random
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.app.guidance.assign import lookup_drive_minutes
from backend.app.guidance.policies import apply_policy
from backend.app.health.train import CONDITIONS_BY_ID, Predictor, get_predictor
from backend.app.notes.generator import NoteFacts, NoteGenerator
from backend.app.routing.graph import RoutingGraph
from backend.app.sim.engine import (
    ANNUAL_SEVERE_HARM_BASELINE,
    BASELINE_HANDOVER_WAIT_MIN,
    SimulationEngine,
)
from backend.app.sim.entities import Ambulance, Hospital, Patient
from backend.app.sim.traffic import Roadblock
from scripts.make_patients import generate_dataset

# Resolve project root and directories reliably across Windows and IBM LinuxONE (s390x)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
HOSPITALS_PATH = DATA_DIR / "hospitals.json"
CONDITIONS_PATH = DATA_DIR / "conditions.json"
PATIENTS_PATH = DATA_DIR / "patients.json"

app = FastAPI(
    title="TRIAGE API",
    description=(
        "Time-critical Routing and Intelligent Ambulance Guidance Engine — "
        "Real-time multi-ambulance severity prediction and joint hospital assignment on IBM LinuxONE."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global singletons
routing_graph: RoutingGraph | None = None
predictor: Predictor | None = None
note_generator: NoteGenerator = NoteGenerator(timeout_s=4.0)

engine: SimulationEngine | None = None
baseline_engine: SimulationEngine | None = None
current_config: dict[str, Any] = {
    "ambulances": 5,
    "policy": "TRIAGE",
    "traffic_level": "normal",
    "hour_of_day": 20.37,  # 8:22 PM default from pitch story
    "seed": 42,
    "speed": 5,  # ticks per wall-clock second (5 ticks/sec = 1 tick per 0.2s)
}
active_roadblocks: list[Roadblock] = []


class StartSimRequest(BaseModel):
    ambulances: int = Field(default=5, ge=1, le=20)
    policy: str = Field(default="TRIAGE")
    traffic_level: str = Field(default="normal")
    hour_of_day: float = Field(default=20.37)
    seed: int = Field(default=42)
    speed: int = Field(default=5, ge=1, le=60)


class SpeedUpdateRequest(BaseModel):
    speed: int = Field(default=5, ge=1, le=60)


class HospitalPatchRequest(BaseModel):
    beds_total: int | None = None
    beds_occupied: int | None = None
    base_wait_min: float | None = None
    theatre_ready: bool | None = None


class RoadblockRequest(BaseModel):
    lat: float
    lon: float
    radius_m: float = 550.0


def _ensure_backends_loaded() -> tuple[RoutingGraph, Predictor]:
    """Lazily initialize the Manchester CSR road graph and HistGradientBoosting model."""
    global routing_graph, predictor
    if routing_graph is None:
        routing_graph = RoutingGraph()
    if predictor is None:
        predictor = get_predictor(seed=42)
    return routing_graph, predictor


def _load_hospitals_list() -> list[Hospital]:
    """Load the 8 Greater Manchester NHS hospitals from data/hospitals.json."""
    if not HOSPITALS_PATH.exists():
        raise FileNotFoundError(f"Missing hospitals file at {HOSPITALS_PATH}")
    raw_list = json.loads(HOSPITALS_PATH.read_text(encoding="utf-8"))
    hospitals = [Hospital.from_dict(item) for item in raw_list]
    return hospitals


def _load_or_generate_patients(seed: int, count: int) -> list[dict[str, Any]]:
    """
    Draw a vivid, realistic mix of emergency patients (prioritizing high-acuity
    STEMI, stroke, trauma, cardiac arrest, ruptured AAA, respiratory failure, etc.)
    so the anti-stampede demo is dramatic and clinically meaningful.
    """
    _, pool = generate_dataset(seed=seed, num_patients=max(40, count * 4))
    rng = random.Random(seed)
    # Weight towards time-critical emergencies for a compelling simulation
    critical_pool = [
        p for p in pool if p["condition_id"] not in ("minor_injury", "long_bone_fracture")
    ]
    chosen: list[dict[str, Any]] = []
    for i in range(count):
        if i < len(critical_pool) and rng.random() < 0.85:
            p_raw = copy.deepcopy(critical_pool[(i * 3 + seed) % len(critical_pool)])
        else:
            p_raw = copy.deepcopy(pool[(i + seed) % len(pool)])
        p_raw["patient_id"] = f"p_{i+1:03d}"
        chosen.append(p_raw)
    return chosen


def _attach_real_road_polylines(
    sim_engine: SimulationEngine,
    rg: RoutingGraph,
    predecessors: Any,
) -> None:
    """Populate `amb.route_coords` with multi-hop Manchester road coordinates."""
    for amb in sim_engine.ambulances:
        if amb.status == "EN_ROUTE" and amb.destination_hospital_id:
            try:
                coords = rg.reconstruct_route_coords(
                    amb.destination_hospital_id,
                    amb.current_node_id,
                    predecessors,
                )
                if len(coords) >= 2:
                    amb.route_coords = coords
                    sim_engine._route_updated_this_tick.add(amb.id)
            except Exception:
                pass


def _build_simulation_pair(req: StartSimRequest) -> tuple[SimulationEngine, SimulationEngine]:
    """
    Build both the primary `SimulationEngine` (using `req.policy`) and a shadow
    `NEAREST` baseline engine on the exact same seed & ambulances so the Impact
    Calculator can show true head-to-head metrics as well as the 30-min NHS baseline!
    """
    rg, pred_model = _ensure_backends_loaded()
    rng = random.Random(req.seed)

    hospitals_main = _load_hospitals_list()
    # Under heavy ambulance waves (e.g. 8-10 ambulances), make inner-city hospitals
    # slightly busier so the stampede problem is immediately visible on the map
    if req.ambulances >= 5:
        for h in hospitals_main:
            if h.id in ("mri", "salford"):
                h.beds_occupied = min(h.beds_total - 1, h.beds_occupied + 1)

    hospitals_shadow = copy.deepcopy(hospitals_main)

    times_sec, predecessors = rg.compute_travel_times(
        traffic_level=req.traffic_level,
        hour_of_day=req.hour_of_day,
        roadblocks=active_roadblocks,
    )

    # Pick non-hospital road nodes across Greater Manchester for spawning ambulances
    candidate_nodes = [
        nid
        for nid in sorted(rg.node_coords.keys())
        if nid not in rg.hospital_nodes and nid > 10
    ]
    # Cluster ~60% of spawns near central/inner Manchester so naive routing stampedes MRI/Salford
    central_nodes = [
        nid
        for nid in candidate_nodes
        if abs(rg.node_coords[nid][0] - 53.475) < 0.045
        and abs(rg.node_coords[nid][1] - (-2.245)) < 0.065
    ]

    patient_dicts = _load_or_generate_patients(seed=req.seed, count=req.ambulances)
    ambulances_main: list[Ambulance] = []

    for idx, p_dict in enumerate(patient_dicts):
        if central_nodes and idx < max(3, int(req.ambulances * 0.65)):
            spawn_node = central_nodes[(idx * 5 + req.seed) % len(central_nodes)]
        else:
            spawn_node = rng.choice(candidate_nodes)

        lat, lon = rg.node_coords[spawn_node]
        s0_score, det_rate = pred_model.predict(p_dict)
        cond_meta = CONDITIONS_BY_ID.get(p_dict["condition_id"], {})

        patient_obj = Patient(
            id=p_dict["patient_id"],
            condition_id=p_dict["condition_id"],
            condition_name=cond_meta.get("name", p_dict["condition_id"].replace("_", " ").title()),
            age=int(p_dict["age"]),
            sex=str(p_dict.get("sex", "M")),
            severity_s0=float(s0_score),
            deterioration_rate_per_min=float(det_rate),
            needs_specialty=cond_meta.get("specialty", "general"),
            needs_theatre=bool(cond_meta.get("theatre_needed", False)),
            vitals=dict(p_dict.get("vitals", {})),
        )

        amb = Ambulance(
            id=f"AMB-{idx+1:02d}",
            patient=patient_obj,
            current_node_id=spawn_node,
            status="EN_ROUTE",
            destination_hospital_id=None,
            lat=round(float(lat), 6),
            lon=round(float(lon), 6),
        )
        ambulances_main.append(amb)

    ambulances_shadow = copy.deepcopy(ambulances_main)

    main_eng = SimulationEngine(
        hospitals=hospitals_main,
        ambulances=ambulances_main,
        travel_time_matrix=times_sec,
        policy_name=req.policy,
    )
    _attach_real_road_polylines(main_eng, rg, predecessors)

    shadow_Policy = "NEAREST" if req.policy.upper() == "TRIAGE" else "TRIAGE"
    shadow_eng = SimulationEngine(
        hospitals=hospitals_shadow,
        ambulances=ambulances_shadow,
        travel_time_matrix=times_sec,
        policy_name=shadow_Policy,
    )
    _attach_real_road_polylines(shadow_eng, rg, predecessors)

    return main_eng, shadow_eng


async def _enrich_notes_with_deepseek(sim_engine: SimulationEngine) -> None:
    """
    Asynchronously upgrade ambulance handover notes using `NoteGenerator` (DeepSeek)
    without ever blocking the 5Hz simulation tick loop.
    """
    hosp_map = {h.id: h for h in sim_engine.hospitals}
    tasks = []

    async def _update_one(amb: Ambulance) -> None:
        h = hosp_map.get(amb.destination_hospital_id or "")
        if not h:
            return
        p = amb.patient
        v = p.vitals or {}
        vitals_str = (
            f"HR {v.get('hr', 95)}, SBP {v.get('sbp', 110)} mmHg, SpO2 {v.get('spo2', 96)}%"
            if v
            else ""
        )
        spec_need = (
            f"{p.needs_specialty.capitalize()} team"
            + (" & theatre needed" if p.needs_theatre else " needed")
            if p.needs_specialty and p.needs_specialty not in ("none", "")
            else "Standard ED bay needed"
        )
        facts = NoteFacts(
            patient_id=p.id,
            age=p.age,
            sex=p.sex,
            condition_name=p.condition_name or p.condition_id,
            severity_s0=amb.current_deterioration,
            deterioration_rate=p.deterioration_rate_per_min,
            category=p.category,
            hospital_name=h.name,
            eta_minutes=max(1, int(round(amb.eta_seconds / 60.0))),
            special_needs=spec_need,
            vitals_summary=vitals_str,
        )
        amb.handover_note = await note_generator.generate(facts)

    for amb in sim_engine.ambulances:
        if amb.status == "EN_ROUTE":
            tasks.append(_update_one(amb))

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def _serialize_enriched_state(sim_engine: SimulationEngine) -> dict[str, Any]:
    """
    Return the Section 7 WebSocket contract enriched with patient condition & vitals
    so the frontend can display rich clickable ambulance & hospital cards.
    """
    state = sim_engine.get_state()
    amb_by_id = {a.id: a for a in sim_engine.ambulances}
    hosp_by_id = {h.id: h for h in sim_engine.hospitals}

    for amb_dict in state["ambulances"]:
        amb_obj = amb_by_id.get(amb_dict["id"])
        if amb_obj:
            p = amb_obj.patient
            dest_h = hosp_by_id.get(amb_obj.destination_hospital_id or "")
            amb_dict["hospital_name"] = dest_h.name if dest_h else "Unassigned"
            amb_dict["patient"] = {
                "id": p.id,
                "age": p.age,
                "sex": p.sex,
                "condition_id": p.condition_id,
                "condition_name": p.condition_name or p.condition_id,
                "severity_s0": p.severity_s0,
                "needs_specialty": p.needs_specialty,
                "needs_theatre": p.needs_theatre,
                "vitals": p.vitals,
            }
            # Always include current route coordinates so new WS clients can render polylines immediately
            if amb_dict.get("route") is None and amb_obj.route_coords:
                amb_dict["route"] = amb_obj.route_coords

    for hosp_dict in state["hospitals"]:
        hosp_obj = hosp_by_id.get(hosp_dict["id"])
        if hosp_obj:
            hosp_dict["base_wait_min"] = hosp_obj.base_wait_min
            hosp_dict["service_min"] = hosp_obj.service_min
            hosp_dict["specialties"] = sorted(hosp_obj.specialties)
            hosp_dict["theatre_ready"] = hosp_obj.theatre_ready

    state["policy"] = sim_engine.policy_name
    state["traffic_level"] = current_config.get("traffic_level", "normal")
    state["hour_of_day"] = current_config.get("hour_of_day", 20.37)
    state["speed"] = current_config.get("speed", 5)
    state["roadblocks"] = [
        {"id": rb.id, "lat": rb.lat, "lon": rb.lon, "radius_m": rb.radius_m}
        for rb in active_roadblocks
    ]
    return state


@app.on_event("startup")
async def startup_event() -> None:
    """Warm up the road graph, ML model, and an initial 5-ambulance scenario on startup."""
    global engine, baseline_engine
    _ensure_backends_loaded()
    default_req = StartSimRequest(ambulances=5, policy="TRIAGE")
    engine, baseline_engine = _build_simulation_pair(default_req)
    # Pause initially so user sees ambulances poised on the map and can press Simulate
    engine.running = False


@app.get("/api/health", tags=["System"])
async def health_check() -> dict[str, Any]:
    """Health check endpoint reporting architecture (e.g. s390x on LinuxONE) and ML model status."""
    rg, pred = _ensure_backends_loaded()
    return {
        "status": "ok",
        "service": "TRIAGE",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "graph_nodes": rg.num_nodes,
        "graph_edges": rg.deduped_edges_count,
        "ml_model_r2": round(pred.train_r2, 4),
        "ml_train_ms": round(pred.train_time_ms, 1),
        "data_ready": {
            "conditions_json": CONDITIONS_PATH.exists(),
            "patients_json": PATIENTS_PATH.exists(),
            "hospitals_json": HOSPITALS_PATH.exists(),
        },
        "disclaimer": "Simulation with synthetic data. Not medical software.",
    }


@app.get("/api/state", tags=["Simulation"])
async def get_current_state() -> dict[str, Any]:
    """Return the current simulation state for immediate map population on page load."""
    global engine, baseline_engine
    if engine is None:
        default_req = StartSimRequest(ambulances=5, policy="TRIAGE")
        engine, baseline_engine = _build_simulation_pair(default_req)
        engine.running = False
    return _serialize_enriched_state(engine)


@app.post("/api/start", tags=["Simulation"])
async def start_simulation(req: StartSimRequest) -> dict[str, Any]:
    """
    Initialize and start a simulation with `ambulances` (e.g. 5 or 10) and `policy`
    ("TRIAGE" or "NEAREST").
    """
    global engine, baseline_engine, current_config
    current_config.update(
        {
            "ambulances": req.ambulances,
            "policy": req.policy.upper(),
            "traffic_level": req.traffic_level,
            "hour_of_day": req.hour_of_day,
            "seed": req.seed,
            "speed": req.speed,
        }
    )
    engine, baseline_engine = _build_simulation_pair(req)
    engine.running = True

    # Fire-and-forget async DeepSeek note generation so notes upgrade seamlessly
    asyncio.create_task(_enrich_notes_with_deepseek(engine))

    return _serialize_enriched_state(engine)


@app.post("/api/spawn", tags=["Simulation"])
async def spawn_preview(req: StartSimRequest) -> dict[str, Any]:
    """
    Spawn N ambulances on the map in a paused state so the user can inspect patients,
    edit hospitals, or drop roadblocks before clicking 'Simulate'.
    """
    global engine, baseline_engine, current_config
    current_config.update(
        {
            "ambulances": req.ambulances,
            "policy": req.policy.upper(),
            "traffic_level": req.traffic_level,
            "hour_of_day": req.hour_of_day,
            "seed": req.seed,
            "speed": req.speed,
        }
    )
    engine, baseline_engine = _build_simulation_pair(req)
    engine.running = False
    asyncio.create_task(_enrich_notes_with_deepseek(engine))
    return _serialize_enriched_state(engine)


@app.post("/api/speed", tags=["Simulation"])
async def set_simulation_speed(req: SpeedUpdateRequest) -> dict[str, Any]:
    """Adjust simulation playback speed multiplier live."""
    current_config["speed"] = req.speed
    return {"status": "ok", "speed": req.speed}


@app.patch("/api/hospital/{hospital_id}", tags=["Simulation"])
async def update_hospital(hospital_id: str, patch: HospitalPatchRequest) -> dict[str, Any]:
    """Live-edit hospital bed capacity, occupied beds, or base wait time and trigger replan."""
    global engine
    if engine is None:
        raise HTTPException(status_code=400, detail="Simulation engine not initialized.")

    hosp = engine._hospital_by_id.get(hospital_id)
    if hosp is None:
        raise HTTPException(status_code=404, detail=f"Hospital '{hospital_id}' not found.")

    if patch.beds_total is not None:
        hosp.beds_total = max(1, int(patch.beds_total))
    if patch.beds_occupied is not None:
        hosp.beds_occupied = max(0, min(hosp.beds_total, int(patch.beds_occupied)))
    if patch.base_wait_min is not None:
        hosp.base_wait_min = max(0.0, float(patch.base_wait_min))
    if patch.theatre_ready is not None:
        hosp.theatre_ready = bool(patch.theatre_ready)

    # Trigger an immediate replan so ambulances react to the edited hospital capacity!
    rg, _ = _ensure_backends_loaded()
    times_sec, preds = rg.compute_travel_times(
        traffic_level=current_config["traffic_level"],
        hour_of_day=current_config["hour_of_day"],
        roadblocks=active_roadblocks,
        sim_time_s=engine.sim_time_s,
    )
    engine.travel_time_matrix = times_sec
    engine._replan_assignments()
    _attach_real_road_polylines(engine, rg, preds)
    asyncio.create_task(_enrich_notes_with_deepseek(engine))

    return _serialize_enriched_state(engine)


@app.post("/api/roadblock", tags=["Simulation"])
async def add_roadblock(req: RoadblockRequest) -> dict[str, Any]:
    """Place a roadblock on the Manchester map and immediately recompute routes & assignments."""
    global engine
    rb = Roadblock(
        id=f"rb_{len(active_roadblocks)+1}_{int(datetime.now().timestamp())}",
        lat=req.lat,
        lon=req.lon,
        radius_m=req.radius_m,
    )
    active_roadblocks.append(rb)

    if engine is not None:
        rg, _ = _ensure_backends_loaded()
        times_sec, preds = rg.compute_travel_times(
            traffic_level=current_config["traffic_level"],
            hour_of_day=current_config["hour_of_day"],
            roadblocks=active_roadblocks,
            sim_time_s=engine.sim_time_s,
        )
        engine.travel_time_matrix = times_sec
        engine._replan_assignments()
        _attach_real_road_polylines(engine, rg, preds)
        engine.events.append(
            {
                "t": engine.sim_time_s,
                "kind": "roadblock",
                "id": rb.id,
                "lat": round(rb.lat, 5),
                "lon": round(rb.lon, 5),
            }
        )

    return _serialize_enriched_state(engine) if engine else {"status": "ok"}


@app.delete("/api/roadblocks", tags=["Simulation"])
async def clear_roadblocks() -> dict[str, Any]:
    """Clear all user-placed roadblocks."""
    active_roadblocks.clear()
    if engine is not None:
        rg, _ = _ensure_backends_loaded()
        times_sec, preds = rg.compute_travel_times(
            traffic_level=current_config["traffic_level"],
            hour_of_day=current_config["hour_of_day"],
            roadblocks=[],
            sim_time_s=engine.sim_time_s,
        )
        engine.travel_time_matrix = times_sec
        engine._replan_assignments()
        _attach_real_road_polylines(engine, rg, preds)
    return _serialize_enriched_state(engine) if engine else {"status": "ok"}


@app.get("/api/impact", tags=["Evaluation"])
async def get_impact_summary() -> dict[str, Any]:
    """
    Return `engine.calculate_impact_summary()` enriched with a side-by-side comparison
    between TRIAGE AI and the Naive Nearest-Hospital policy on the exact same scenario.
    """
    global engine, baseline_engine
    if engine is None:
        default_req = StartSimRequest(ambulances=5, policy="TRIAGE")
        engine, baseline_engine = _build_simulation_pair(default_req)

    primary_impact = engine.calculate_impact_summary()
    shadow_impact = (
        baseline_engine.calculate_impact_summary()
        if baseline_engine is not None
        else primary_impact
    )

    if engine.policy_name == "TRIAGE":
        triage_summary = primary_impact
        nearest_summary = shadow_impact
        triage_eng = engine
        nearest_eng = baseline_engine or engine
    else:
        nearest_summary = primary_impact
        triage_summary = shadow_impact
        nearest_eng = engine
        triage_eng = baseline_engine or engine

    def _compute_detailed_metrics(sim_eng: SimulationEngine) -> dict[str, Any]:
        slot_counts: dict[str, int] = {h.id: 0 for h in sim_eng.hospitals}
        corridor_overflows = 0
        specialty_mismatches = 0
        total_det_at_treatment = 0.0
        total_time_to_treatment = 0.0

        for idx, amb in enumerate(sim_eng.ambulances):
            h_id = amb.destination_hospital_id
            hosp = sim_eng._hospital_by_id.get(h_id or "")
            if not hosp:
                continue
            k = slot_counts[h.id if (h := hosp) else ""]
            slot_counts[hosp.id] += 1

            drive_m = lookup_drive_minutes(
                sim_eng.travel_time_matrix,
                amb,
                hosp,
                idx,
                sim_eng._hospital_idx_by_id[hosp.id],
            )
            wait_m = float(hosp.base_wait_min) + k * float(hosp.service_min)
            if k >= hosp.beds_free:
                corridor_overflows += 1
                wait_m += 30.0
            needed = (amb.patient.needs_specialty or "").lower()
            if needed and needed not in ("none", "") and needed not in hosp.specialties:
                specialty_mismatches += 1
                wait_m += 45.0

            tot_m = drive_m + wait_m
            total_time_to_treatment += tot_m
            total_det_at_treatment += min(
                100.0,
                amb.patient.severity_s0 + amb.patient.deterioration_rate_per_min * tot_m,
            )

        n = max(1, len(sim_eng.ambulances))
        return {
            "avg_time_to_treatment_min": round(total_time_to_treatment / n, 1),
            "mean_deterioration_at_treatment": round(total_det_at_treatment / n, 1),
            "corridor_overflows": corridor_overflows,
            "specialty_mismatches": specialty_mismatches,
        }

    triage_details = _compute_detailed_metrics(triage_eng)
    nearest_details = _compute_detailed_metrics(nearest_eng)

    diversions_count = sum(1 for ev in engine.events if ev.get("kind") == "diversion")

    return {
        **primary_impact,
        "active_policy": engine.policy_name,
        "ambulances_count": len(engine.ambulances),
        "diversions_count": diversions_count,
        "traffic_level": current_config.get("traffic_level", "normal"),
        "hour_of_day": current_config.get("hour_of_day", 20.37),
        "triage_comparison": {
            "triage_handover_min": triage_summary["triage_avg_handover_min"],
            "nearest_handover_min": nearest_summary["triage_avg_handover_min"],
            "triage_projected_cases": triage_summary["projected_annual_severe_cases"],
            "nearest_projected_cases": nearest_summary["projected_annual_severe_cases"],
            "triage_prevented": triage_summary["severe_cases_prevented"],
            "nearest_prevented": nearest_summary["severe_cases_prevented"],
            "triage_reduction_pct": triage_summary["reduction_percent"],
            "nearest_reduction_pct": nearest_summary["reduction_percent"],
            "triage_details": triage_details,
            "nearest_details": nearest_details,
        },
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    5Hz wall-clock WebSocket loop (`await asyncio.sleep(0.2)`):
      - Streams live `engine.tick()` states while `engine.running` is True.
      - Supports multi-step fast-forward per wall tick (`speed` parameter) so a
        15-minute Manchester drive can complete in ~20 seconds during a live demo!
    """
    global engine, baseline_engine
    await websocket.accept()

    if engine is None:
        default_req = StartSimRequest(ambulances=5, policy="TRIAGE")
        engine, baseline_engine = _build_simulation_pair(default_req)
        engine.running = False

    try:
        # Immediately push initial snapshot on connection
        await websocket.send_json(_serialize_enriched_state(engine))

        while True:
            if engine is not None and engine.running:
                # Advance simulation steps per 0.2s wall tick based on selected speed
                # speed=5 -> 1 sim second per 0.2s (5x real-time)
                # speed=15 -> 3 sim seconds per 0.2s (15x real-time)
                # speed=30 -> 6 sim seconds per 0.2s (30x real-time)
                steps_per_frame = max(1, int(round(current_config.get("speed", 5) / 5)))
                for _ in range(steps_per_frame):
                    if not engine.running:
                        break
                    prev_events_len = len(engine.events)
                    engine.tick()
                    # If a 15-second replan caused a diversion, reconstruct real road coordinates
                    if len(engine.events) > prev_events_len:
                        new_evs = engine.events[prev_events_len:]
                        if any(e.get("kind") == "diversion" for e in new_evs):
                            rg, _ = _ensure_backends_loaded()
                            _, preds = rg.compute_travel_times(
                                traffic_level=current_config["traffic_level"],
                                hour_of_day=current_config["hour_of_day"],
                                roadblocks=active_roadblocks,
                                sim_time_s=engine.sim_time_s,
                            )
                            _attach_real_road_polylines(engine, rg, preds)
                            asyncio.create_task(_enrich_notes_with_deepseek(engine))

                await websocket.send_json(_serialize_enriched_state(engine))

            await asyncio.sleep(0.2)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass


# Mount the `frontend/` directory at `/` LAST so `/api/*` and `/ws` take priority
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")