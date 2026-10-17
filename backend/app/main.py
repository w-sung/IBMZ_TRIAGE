"""
TRIAGE — Time-critical Routing and Intelligent Ambulance Guidance Engine
FastAPI Backend Entry Point (Chunk 1: Skeleton & Health Check)

Designed for IBM Z / LinuxONE (s390x) and local x86/Windows development.
"""

from datetime import datetime, timezone
from pathlib import Path
import platform
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Resolve project root and data directory paths reliably across Windows and LinuxONE
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
CONDITIONS_PATH = DATA_DIR / "conditions.json"
PATIENTS_PATH = DATA_DIR / "patients.json"

app = FastAPI(
    title="TRIAGE API",
    description=(
        "Time-critical Routing and Intelligent Ambulance Guidance Engine — "
        "Real-time multi-ambulance severity prediction and joint hospital assignment on IBM LinuxONE."
    ),
    version="0.1.0",
)

# Enable CORS so the frontend (Leaflet.js UI) can communicate with the backend freely
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Root"])
async def root() -> Dict[str, str]:
    """Root informational endpoint."""
    return {
        "service": "TRIAGE — Emergency Ambulance Routing & Guidance Engine",
        "status": "online",
        "health_endpoint": "/api/health",
        "disclaimer": "Simulation with synthetic data. Not medical software.",
    }


@app.get("/api/health", tags=["System"])
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint used by the frontend and Docker container checks.
    Also reports runtime architecture (e.g. s390x on IBM LinuxONE) and data readiness.
    """
    return {
        "status": "ok",
        "service": "TRIAGE",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "data_ready": {
            "conditions_json": CONDITIONS_PATH.exists(),
            "patients_json": PATIENTS_PATH.exists(),
        },
        "disclaimer": "Simulation with synthetic data. Not medical software.",
    }