# TRIAGE - Development Log & AI Handoff
**Branch:** `arno-dev-branch`
**Author:** Arno
**Current Phase:** Chunk 1 Completed (Foundation & Synthetic Data)

## 1. What Has Been Built
- **FastAPI Skeleton:** Created the core backend server (`backend/app/main.py`) with CORS enabled and a `/api/health` endpoint. The health endpoint actively checks for system architecture (ready for s390x) and verifies if the data files exist.
- **Synthetic Patient Generator:** Created a deterministic script (`scripts/make_patients.py`) to generate 100% synthetic, clinical-grade patients with realistic vitals based on 20 emergency conditions outlined in `CONTEXT.md`.

## 2. How to Run the Code
**To generate the patient data:**
```bash
python scripts/make_patients.py
# Optional arguments: --seed 42 --count 100  


Inputs: scripts/make_patients.py takes optional CLI arguments --seed (default 42) and --count (default 100).
Outputs: Generates two files in the data/ directory:
data/conditions.json (Catalog of the 20 conditions with their profiles).
data/patients.json (The generated patients ready to be routed).
4. Key Variables & Schema (ATTENTION CLAUDE/AI)
To avoid merge conflicts and duplicated logic, use these exact schemas and variable names:
FastAPI App Instance: app in backend/app/main.py.
Global Paths: PROJECT_ROOT, DATA_DIR, CONDITIONS_PATH, PATIENTS_PATH are already resolved dynamically in main.py using pathlib.

Here is what a Patient Schema looks like:

{
  "patient_id": "p_001",
  "age": 68,
  "sex": "F",
  "condition_id": "stemi",
  "vitals": {
    "hr": int, "sbp": int, "rr": int, "spo2": int, "etco2": int,
    "spco": float, "methb": float, "ecg_rhythm": str, 
    "st_elevation": bool, "consciousness": str
  }
}

