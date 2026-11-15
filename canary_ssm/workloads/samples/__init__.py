"""Reviewed sample microservices for isolated worker execution."""
from pathlib import Path

SAMPLES_DIR = Path(__file__).resolve().parent
CLEAN_SERVICE_SCRIPT = SAMPLES_DIR / "clean_service.py"
LEAKING_SERVICE_SCRIPT = SAMPLES_DIR / "leaking_service.py"
