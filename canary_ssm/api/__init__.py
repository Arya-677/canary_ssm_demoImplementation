"""API package for Virtual Data Center Simulator and Canary Detection."""
from __future__ import annotations

from .app import create_app, run_server
from .routes import router, get_service, set_service
from .service import SimulatorService

__all__ = [
    "SimulatorService",
    "create_app",
    "get_service",
    "router",
    "run_server",
    "set_service",
]
