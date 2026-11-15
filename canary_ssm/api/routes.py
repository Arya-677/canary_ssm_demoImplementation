"""FastAPI Router for Virtual Data Center Simulator Endpoints."""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from .service import SimulatorService

router = APIRouter(prefix="/api")

# Singleton service instance (initialized on app start)
_service: SimulatorService | None = None


def get_service() -> SimulatorService:
    global _service
    if _service is None:
        _service = SimulatorService()
    return _service


def set_service(svc: SimulatorService) -> None:
    global _service
    _service = svc


# ---------------------------------------------------------------------
# Request & Response Schemas
# ---------------------------------------------------------------------
class WorldControlRequest(BaseModel):
    action: str = Field(..., description="Action: start, pause, step, reset, speed")
    ticks: int = Field(1, description="Number of ticks for step action")
    speed_seconds: float = Field(1.0, description="Seconds per tick for speed action")
    seed: int | None = Field(None, description="Optional seed for reset action")


class CreateReleaseRequest(BaseModel):
    release_id: str
    version_tag: str
    behavior_profile: dict[str, Any]
    artifact_filename: str | None = None
    artifact_content: str | None = None
    metadata: dict[str, Any] | None = None


class ValidateAllocationRequest(BaseModel):
    canary_server_ids: list[str]


class DeployCanaryRequest(BaseModel):
    release_id: str
    canary_server_ids: list[str] | None = None


class RollbackCanaryRequest(BaseModel):
    release_id: str
    restart_process: bool = True


class PauseCanaryRequest(BaseModel):
    release_id: str
    reason: str = "Operator paused rollout"


class PromoteCanaryRequest(BaseModel):
    release_id: str
    reason: str = "Operator promoted rollout"


class InjectFaultRequest(BaseModel):
    fault_type: str
    scope: str
    target_id: str
    severity: float
    duration: int = 60
    onset_tick: int | None = None
    susceptible_class_id: int | None = None
    target_version: str | None = None
    parameters: dict[str, Any] | None = None


class ConfigureHazardsRequest(BaseModel):
    enable_stochastic: bool
    server_outage_hazard_per_min: float | None = None
    rack_latency_hazard_per_min: float | None = None
    seed: int | None = None


class ToggleDetectorRequest(BaseModel):
    connected: bool | None = None


class AutoRollbackRequest(BaseModel):
    enabled: bool


class ImportRunRequest(BaseModel):
    bundle: dict[str, Any]


class LoadScenarioRequest(BaseModel):
    name: str | None = Field(None, description="Canonical scenario name from catalog")
    scenario_name: str | None = Field(None, description="Alias for scenario name")

    @model_validator(mode="after")
    def resolve_name(self) -> LoadScenarioRequest:
        if not self.name and not self.scenario_name:
            raise ValueError("Either 'name' or 'scenario_name' must be provided")
        if not self.name:
            self.name = self.scenario_name
        return self


# ---------------------------------------------------------------------
# World & Clock Routes
# ---------------------------------------------------------------------
@router.get("/world/status")
def get_world_status() -> dict[str, Any]:
    return get_service().get_status()


@router.post("/world/control")
def control_world(req: WorldControlRequest) -> dict[str, Any]:
    svc = get_service()
    action = req.action.lower()
    if action == "start":
        return svc.start()
    elif action == "pause":
        return svc.pause()
    elif action == "step":
        return svc.step(max(1, req.ticks))
    elif action == "reset":
        return svc.reset(req.seed)
    elif action == "speed":
        return svc.set_speed(req.speed_seconds)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown control action {req.action!r}")


@router.get("/world/servers")
def get_servers() -> list[dict[str, Any]]:
    return get_service().get_servers()


@router.get("/world/racks")
def get_racks() -> list[dict[str, Any]]:
    return get_service().get_racks()


# ---------------------------------------------------------------------
# Releases & Deployments Routes
# ---------------------------------------------------------------------
@router.get("/releases")
def list_releases() -> list[dict[str, Any]]:
    return get_service().list_releases()


@router.post("/releases")
def create_release(req: CreateReleaseRequest) -> dict[str, Any]:
    try:
        return get_service().create_release(
            release_id=req.release_id,
            version_tag=req.version_tag,
            behavior_profile=req.behavior_profile,
            artifact_filename=req.artifact_filename,
            artifact_content=req.artifact_content,
            metadata=req.metadata,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/releases/default-allocation")
def get_default_allocation() -> dict[str, Any]:
    return get_service().get_default_allocation()


@router.post("/releases/validate")
def validate_allocation(req: ValidateAllocationRequest) -> dict[str, Any]:
    return get_service().validate_allocation(req.canary_server_ids)


@router.post("/releases/deploy")
def deploy_canary(req: DeployCanaryRequest) -> dict[str, Any]:
    try:
        return get_service().deploy_canary(
            release_id=req.release_id,
            canary_server_ids=req.canary_server_ids,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/releases/rollback")
def rollback_canary(req: RollbackCanaryRequest) -> dict[str, Any]:
    try:
        return get_service().rollback_canary(
            release_id=req.release_id,
            restart_process=req.restart_process,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/releases/pause")
def pause_canary(req: PauseCanaryRequest) -> dict[str, Any]:
    try:
        return get_service().pause_canary(
            release_id=req.release_id,
            reason=req.reason,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/releases/promote")
def promote_canary(req: PromoteCanaryRequest) -> dict[str, Any]:
    try:
        return get_service().promote_canary(
            release_id=req.release_id,
            reason=req.reason,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------
# Fault Lab Routes (Developer View)
# ---------------------------------------------------------------------
@router.post("/faults/inject")
def inject_fault(req: InjectFaultRequest) -> dict[str, Any]:
    try:
        return get_service().inject_fault(
            fault_type=req.fault_type,
            scope=req.scope,
            target_id=req.target_id,
            severity=req.severity,
            duration=req.duration,
            onset_tick=req.onset_tick,
            susceptible_class_id=req.susceptible_class_id,
            target_version=req.target_version,
            parameters=req.parameters,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/faults/hazards")
def configure_hazards(req: ConfigureHazardsRequest) -> dict[str, Any]:
    return get_service().configure_hazards(
        enable_stochastic=req.enable_stochastic,
        server_outage_hazard_per_min=req.server_outage_hazard_per_min,
        rack_latency_hazard_per_min=req.rack_latency_hazard_per_min,
        seed=req.seed,
    )


@router.get("/faults/truth")
def get_fault_truth() -> dict[str, Any]:
    """Developer view: returns ground truth fault events."""
    return get_service().get_fault_truth()


# ---------------------------------------------------------------------
# Command History & Audit
# ---------------------------------------------------------------------
@router.get("/commands/history")
def get_command_history() -> list[dict[str, Any]]:
    return get_service().get_command_history()


# ---------------------------------------------------------------------
# Detector Connection Toggle & Operational Modes
# ---------------------------------------------------------------------
@router.post("/detector/toggle")
def toggle_detector(req: ToggleDetectorRequest) -> dict[str, Any]:
    connected = get_service().toggle_detector(req.connected)
    return {"ssm_connected": connected}


@router.post("/detector/auto-rollback")
def set_auto_rollback(req: AutoRollbackRequest) -> dict[str, Any]:
    enabled = get_service().set_auto_rollback(req.enabled)
    return {"auto_rollback_enabled": enabled}


@router.get("/detector/status")
def get_detector_status() -> dict[str, Any]:
    return get_service().get_detector_status()


@router.get("/detector/evidence")
def get_detector_evidence() -> dict[str, Any]:
    return get_service().get_detector_evidence()


@router.get("/detector/compare-methods")
def get_comparison_evidence() -> dict[str, Any]:
    """Side-by-side comparison of Hierarchical, Independent, and Pooled SSM."""
    return get_service().get_comparison_evidence()


@router.get("/detector/timeline")
def get_detector_timeline(limit: int = Query(120, ge=1, le=1000)) -> list[dict[str, Any]]:
    return get_service().get_detector_timeline(limit=limit)


# ---------------------------------------------------------------------
# Scenario Catalog & Guided Presets
# ---------------------------------------------------------------------
@router.get("/scenarios")
def list_scenarios() -> list[dict[str, Any]]:
    return get_service().list_scenarios()


@router.post("/scenarios/load")
def load_scenario(req: LoadScenarioRequest) -> dict[str, Any]:
    try:
        return get_service().load_scenario(req.name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------
# Run Export & Replay Import
# ---------------------------------------------------------------------
@router.get("/runs/export")
def export_run() -> dict[str, Any]:
    return get_service().export_run()


@router.post("/runs/import")
def import_run(req: ImportRunRequest) -> dict[str, Any]:
    return get_service().import_run(req.bundle)


# ---------------------------------------------------------------------
# Monitoring & Telemetry Routes
# ---------------------------------------------------------------------
@router.get("/monitoring/latest")
def get_latest_telemetry() -> list[dict[str, Any]]:
    return get_service().get_latest_telemetry()


@router.get("/monitoring/timeline")
def get_metrics_timeline(limit: int = Query(120, ge=1, le=1000)) -> list[dict[str, Any]]:
    return get_service().get_metrics_timeline(limit=limit)


@router.get("/monitoring/advisory")
def get_advisory() -> dict[str, Any]:
    return get_service().evaluate_advisories()


# ---------------------------------------------------------------------
# Evaluation Routes
# ---------------------------------------------------------------------
@router.get("/evaluation/summary")
def get_evaluation_summary() -> dict[str, Any]:
    svc = get_service()
    adv = svc.evaluate_advisories()
    truth = svc.get_fault_truth()
    status = svc.get_status()

    # Compare detector decision to truth
    active_release_faults = [
        f for f in truth.get("injected_faults", [])
        if f.get("category") == "RELEASE" or "LEAK" in f.get("fault_type", "") or "REGRESSION" in f.get("fault_type", "")
    ]
    has_true_release_fault = (len(active_release_faults) > 0)
    detector_paused = (adv["canary_release_advisory"] == "PAUSE RECOMMENDED")

    return {
        "tick": status["tick"],
        "has_true_release_fault": has_true_release_fault,
        "detector_recommends_pause": detector_paused,
        "infrastructure_advisory": adv["infrastructure_advisory"],
        "canary_release_advisory": adv["canary_release_advisory"],
        "release_score": adv["release_score"],
        "alert_threshold": adv["alert_threshold"],
        "channel_evidence": adv.get("channel_evidence", {}),
        "total_active_faults": truth.get("total_active_faults", 0),
        "total_recorded_ticks": len(svc.tick_metrics_summary),
    }
