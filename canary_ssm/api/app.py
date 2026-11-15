"""FastAPI application factory and static dashboard mounting."""
from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routes import router, get_service, set_service
from .service import SimulatorService


def create_app(service: SimulatorService | None = None) -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="Virtual Data Center & Canary Detection API",
        version="0.2.0",
        description="Hierarchical SSM Canary Regression Detection & Virtual Data Center Simulator",
    )

    # Safe localhost-restricted CORS defaults
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    if service is not None:
        set_service(service)

    # Include REST API routes
    app.include_router(router)

    # Mount static dashboard if directory exists
    dashboard_dir = Path(__file__).resolve().parent.parent / "dashboard"
    if dashboard_dir.exists():
        index_file = dashboard_dir / "index.html"

        @app.get("/", include_in_schema=False)
        async def serve_index():
            if index_file.exists():
                return FileResponse(index_file)
            return {"message": "Virtual Data Center API is running. Dashboard index.html not found."}

        app.mount("/static", StaticFiles(directory=str(dashboard_dir)), name="dashboard_static")

    return app


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start uvicorn server serving the API and Dashboard."""
    import uvicorn
    app = create_app()
    uvicorn.run(app, host=host, port=port)
