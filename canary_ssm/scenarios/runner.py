"""Scenario execution engine with separate artifact persistence.

Persists:
1. manifest.json: Scenario configuration and environment metadata.
2. telemetry.csv: Raw multi-metric observations.
3. model_policy.json: Model and policy identifiers and thresholds.
4. recommendations.csv: Streaming detector outputs and advisories per tick.
5. evaluator_results.json: Evaluator truth comparison and classification metrics.
"""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from canary_ssm.deployments import BehaviorProfile, BehaviorProfileType, Release, ReleaseArtifact
from canary_ssm.detector_service import DetectorService, FrozenPolicy
from canary_ssm.evaluation.fixtures import (
    EventLabel,
    MultiMetricEventTruth,
    classify_run,
    compute_localization,
    evaluate_event_truth,
)
from canary_ssm.faults.engine import FaultEngine
from canary_ssm.faults.models import FaultCategory, FaultDefinition, FaultScope, FaultType
from canary_ssm.telemetry.records import TelemetryRecord
from canary_ssm.world import VirtualWorld, create_default_fleet
from canary_ssm.world.telemetry import HealthyTelemetryConfig, HealthyTelemetryEngine

from .models import ScenarioDefinition


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return f if np.isfinite(f) else None
    except (ValueError, TypeError):
        return None


@dataclass
class ScenarioRunResult:
    """Complete result bundle for an executed scenario."""
    scenario_name: str
    manifest: dict[str, Any]
    telemetry: list[TelemetryRecord]
    model_policy: dict[str, Any]
    recommendations: list[dict[str, Any]]
    evaluator_results: dict[str, Any]
    output_dir: Path | None = None


def run_scenario(
    scenario: ScenarioDefinition,
    output_dir: str | Path | None = None,
    ssm_connected: bool = True,
    policy: FrozenPolicy | None = None,
) -> ScenarioRunResult:
    """Execute scenario from t=0 to horizon_ticks and optionally persist all 5 artifacts."""
    pol = policy or FrozenPolicy()
    out_path = Path(output_dir) if output_dir else None
    if out_path:
        out_path.mkdir(parents=True, exist_ok=True)

    # 1. Initialize Fleet & World Topology
    topo = scenario.topology
    fleet = create_default_fleet(
        n_racks=topo.n_racks,
        servers_per_rack=topo.servers_per_rack,
        n_classes=topo.n_classes,
    )
    all_server_ids = [s.server_id for s in fleet.list_servers()]
    server_meta = {
        s.server_id: {
            "server_id": s.server_id,
            "rack_id": s.rack_id,
            "class_id": s.class_id,
            "memory_capacity_mb": s.memory_capacity_mb,
            "base_latency_ms": s.base_latency_ms,
        }
        for s in fleet.list_servers()
    }

    # 2. Configure Telemetry Engine
    wl = scenario.workload
    t_cfg = HealthyTelemetryConfig(
        nominal_requests=int(wl.base_request_rate),
        gc_period_ticks=wl.gc_period_ticks,
        gc_amplitude_mb=wl.gc_amplitude_mb if wl.has_gc_cycles else 0.0,
        warmup_ticks=wl.warmup_ticks,
        warmup_amplitude_mb=wl.warmup_amplitude_mb,
    )
    telem_engine = HealthyTelemetryEngine(config=t_cfg, seed=scenario.seed)

    # 3. Configure Fault Engine
    fault_engine = FaultEngine(seed=scenario.seed + 100)
    inj = scenario.injection
    dur = (inj.stop_tick - inj.start_tick) if inj.stop_tick else (scenario.horizon_ticks - inj.start_tick)
    dur = max(dur, 1)

    if inj.fault_type == "PROCESS_MEMORY_LEAK":
        target_ids = (
            inj.target_scope.split(",") if inj.target_scope and inj.target_scope != "fleet"
            else scenario.deployment.affected_canary_ids
        )
        for idx, sid in enumerate(target_ids):
            fault_engine.register_manual_fault(FaultDefinition(
                fault_id=f"fault-leak-{idx}",
                fault_type=FaultType.PROCESS_MEMORY_LEAK,
                scope=FaultScope.SERVER,
                target_id=sid,
                onset_tick=inj.start_tick,
                duration=dur,
                severity=inj.severity,
                target_version=scenario.deployment.version,
            ))
    elif inj.fault_type == "RACK_NETWORK_LATENCY":
        target_rack = inj.target_scope or "rack-0"
        fault_engine.register_manual_fault(FaultDefinition(
            fault_id="fault-rack",
            fault_type=FaultType.RACK_NETWORK_LATENCY,
            scope=FaultScope.RACK,
            target_id=target_rack,
            onset_tick=inj.start_tick,
            duration=dur,
            severity=inj.severity,
        ))
    elif inj.fault_type == "FLEET_DEMAND_SPIKE":
        fault_engine.register_manual_fault(FaultDefinition(
            fault_id="fault-fleet",
            fault_type=FaultType.FLEET_DEMAND_SPIKE,
            scope=FaultScope.FLEET,
            target_id="fleet",
            onset_tick=inj.start_tick,
            duration=dur,
            severity=inj.severity,
        ))
    elif inj.fault_type == "CPU_SATURATION":
        target_ids = scenario.deployment.canary_ids if inj.target_scope == "canaries" else all_server_ids
        for idx, sid in enumerate(target_ids):
            fault_engine.register_manual_fault(FaultDefinition(
                fault_id=f"fault-cpu-{idx}",
                fault_type=FaultType.CPU_SATURATION,
                scope=FaultScope.SERVER,
                target_id=sid,
                onset_tick=inj.start_tick,
                duration=dur,
                severity=inj.severity,
                target_version=scenario.deployment.version,
            ))

    # Also handle compound faults (e.g. combined rack fault + leak)
    if scenario.name == "combined_rack_fault_release_leak":
        for idx, sid in enumerate(scenario.deployment.affected_canary_ids):
            fault_engine.register_manual_fault(FaultDefinition(
                fault_id=f"fault-leak-compound-{idx}",
                fault_type=FaultType.PROCESS_MEMORY_LEAK,
                scope=FaultScope.SERVER,
                target_id=sid,
                onset_tick=scenario.deployment.deploy_tick,
                duration=dur,
                severity=35.0,
                target_version=scenario.deployment.version,
            ))

    # 4. Initialize Decoupled Detector Service
    det_service = DetectorService(
        expected_servers=all_server_ids,
        server_metadata=server_meta,
        frozen_policy=pol,
        ssm_connected=ssm_connected,
    )

    # 5. Simulation Execution Loop
    all_telemetry: list[TelemetryRecord] = []
    recommendations: list[dict[str, Any]] = []
    deployed = False
    dep_cfg = scenario.deployment
    t0 = dep_cfg.deploy_tick
    h_ticks = scenario.horizon_ticks

    # Pre-seed RNG for missingness
    rng_miss = np.random.default_rng(scenario.seed + 999)

    for t in range(h_ticks):
        # Deployment event
        if t == t0 and not deployed:
            deployed = True
            for srv_id in dep_cfg.canary_ids:
                server = fleet.get_server(srv_id)
                if server:
                    server.installed_version = dep_cfg.version
            det_service.set_deployment(
                release_id=dep_cfg.release_id,
                canary_ids=dep_cfg.canary_ids,
                t0=t0,
            )

        # Evaluate active faults
        fault_deltas = fault_engine.evaluate_tick_faults(fleet=fleet, tick=t)

        # Generate tick telemetry
        raw_recs = telem_engine.generate_tick_telemetry(
            fleet=fleet,
            tick=t,
            run_id=f"run-{scenario.name}",
            fault_deltas=fault_deltas,
        )

        # Apply missingness or control dropping if configured
        admitted_recs: list[TelemetryRecord] = []
        for rec in raw_recs:
            if inj.drop_same_rack_controls and rec.rack_id == "rack-0" and not rec.exposure:
                # Suppress rack-0 controls to test identifiability abstention
                continue
            if inj.missingness_rate > 0.0 and rng_miss.uniform() < inj.missingness_rate:
                # Random missing observation
                continue
            admitted_recs.append(rec)

        all_telemetry.extend(raw_recs)

        # Stream causality: ingest admitted records and step detector
        det_service.ingest(admitted_recs)
        step_res = det_service.step(t)

        # Record recommendation state
        score_lat_f = _safe_float(step_res.score_lat)
        score_mem_f = _safe_float(step_res.score_mem)
        thresh_lat_f = _safe_float(step_res.threshold_lat)
        thresh_mem_f = _safe_float(step_res.threshold_mem)
        rel_score_f = _safe_float(step_res.release_score)
        eff_mean_f = _safe_float(step_res.canary_effect_mean)
        eff_ci_low_f = _safe_float(step_res.canary_effect_ci_lower)
        eff_ci_upp_f = _safe_float(step_res.canary_effect_ci_upper)

        lat_alarm = bool(score_lat_f is not None and thresh_lat_f is not None and score_lat_f > thresh_lat_f)
        mem_alarm = bool(score_mem_f is not None and thresh_mem_f is not None and score_mem_f > thresh_mem_f)

        recom_entry: dict[str, Any] = {
            "tick": t,
            "eligible": step_res.eligible,
            "latency_release_score": round(rel_score_f, 4) if rel_score_f is not None else None,
            "score_lat": round(score_lat_f, 4) if score_lat_f is not None else None,
            "latency_alarm": lat_alarm,
            "score_mem": round(score_mem_f, 4) if score_mem_f is not None else None,
            "memory_alarm": mem_alarm,
            "infrastructure_advisory": step_res.infrastructure_advisory,
            "canary_release_advisory": step_res.canary_release_advisory,
            "inferred_attribution": step_res.attribution,
            "first_alarm_tick": step_res.first_alert_tick,
            "advisory_reason": step_res.advisory_reason,
            "canary_effect_mean": round(eff_mean_f, 4) if eff_mean_f is not None else None,
            "canary_effect_ci_lower": round(eff_ci_low_f, 4) if eff_ci_low_f is not None else None,
            "canary_effect_ci_upper": round(eff_ci_upp_f, 4) if eff_ci_upp_f is not None else None,
        }
        recommendations.append(recom_entry)

    # 6. Evaluator Results (Evaluator Ground Truth)
    # Extract true event label and affected IDs
    if inj.fault_type == "PROCESS_MEMORY_LEAK" or scenario.name == "combined_rack_fault_release_leak":
        true_label = (
            EventLabel.HARM_MEMORY_GROWTH
            if inj.fault_type != "RACK_NETWORK_LATENCY"
            else EventLabel.HARM_COMPOUND
        )
        affected_hosts = list(scenario.deployment.affected_canary_ids)
    elif inj.fault_type == "RACK_NETWORK_LATENCY":
        true_label = EventLabel.FAULT_RACK_LATENCY
        affected_hosts = []
    elif inj.fault_type == "CPU_SATURATION":
        true_label = EventLabel.HARM_CPU_SATURATION
        affected_hosts = list(scenario.deployment.canary_ids)
    elif inj.fault_type == "FLEET_DEMAND_SPIKE":
        true_label = EventLabel.FAULT_FLEET_DEMAND
        affected_hosts = []
    elif scenario.name == "healthy_gc":
        true_label = EventLabel.HEALTHY_GC_CYCLES
        affected_hosts = []
    else:
        true_label = EventLabel.NO_EVENT
        affected_hosts = []

    # First alarm tick
    alarm_tick = None
    for r in recommendations:
        if r["canary_release_advisory"] in ("PAUSE RECOMMENDED", "ROLLED BACK"):
            alarm_tick = r["tick"]
            break

    # Classification
    has_harm = true_label in (
        EventLabel.HARM_LATENCY_PERSISTENT,
        EventLabel.HARM_MEMORY_GROWTH,
        EventLabel.HARM_CPU_SATURATION,
        EventLabel.HARM_ERROR_REGRESSION,
        EventLabel.HARM_COMPOUND,
    )
    event_truth = MultiMetricEventTruth(
        has_event=has_harm,
        event_label=true_label,
        onset=t0 if has_harm else None,
        intervals=[(t0, h_ticks)] if has_harm else [],
        affected_canary_ids=affected_hosts,
    )
    classification = classify_run(
        t_alarm=alarm_tick,
        truth=event_truth,
        total_ticks=h_ticks,
        exposure_tick=t0,
    )

    # Localization
    loc_metrics: dict[str, float] = {
        "topk_recall": 1.0 if not affected_hosts else 0.0,
        "precision": 1.0 if not affected_hosts else 0.0,
        "recall": 1.0 if not affected_hosts else 0.0,
        "f1": 1.0 if not affected_hosts else 0.0,
    }
    if affected_hosts and ssm_connected:
        latest_ev = det_service.get_evidence()
        host_risks = {s: (latest_ev[s].host_risk or 0.0) for s in dep_cfg.canary_ids if s in latest_ev}
        loc_res = compute_localization(host_risks, affected_hosts, canary_order=dep_cfg.canary_ids, topk=3)
        loc_metrics = {k: round(v, 4) for k, v in loc_res.items() if k in loc_metrics}

    evaluator_results: dict[str, Any] = {
        "scenario_name": scenario.name,
        "true_event_label": true_label.value,
        "true_affected_hosts": affected_hosts,
        "alarm_tick": alarm_tick,
        "detection_status": classification["status"],
        "detection_delay": classification["delay"],
        "capped_time_to_success": classification["capped_time"],
        "localization": loc_metrics,
        "final_infrastructure_advisory": recommendations[-1]["infrastructure_advisory"],
        "final_canary_release_advisory": recommendations[-1]["canary_release_advisory"],
        "final_attribution": recommendations[-1]["inferred_attribution"],
    }

    # 7. Model and Policy Manifest
    model_policy: dict[str, Any] = {
        "model_id": pol.model_id,
        "policy_id": pol.policy_id,
        "alpha": pol.alpha,
        "threshold_latency": pol.threshold_lat,
        "threshold_memory": pol.threshold_mem,
        "persistence_window_ticks": pol.persistence_window,
        "kappa_latency_boundary": pol.kappa_lat,
        "kappa_memory_mb_per_min": pol.kappa_mem,
        "epistemic_disclaimer": pol.epistemic_disclaimer,
    }

    manifest_dict = scenario.to_dict()

    # 8. Persist Artifacts Separately If Requested
    if out_path:
        # A. manifest.json
        (out_path / "manifest.json").write_text(json.dumps(manifest_dict, indent=2) + "\n", encoding="utf-8")

        # B. model_policy.json
        (out_path / "model_policy.json").write_text(json.dumps(model_policy, indent=2) + "\n", encoding="utf-8")

        # C. evaluator_results.json
        (out_path / "evaluator_results.json").write_text(json.dumps(evaluator_results, indent=2) + "\n", encoding="utf-8")

        # D. recommendations.csv
        rec_fields = list(recommendations[0].keys())
        with open(out_path / "recommendations.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=rec_fields)
            w.writeheader()
            w.writerows(recommendations)

        # E. telemetry.csv
        telem_fields = [
            "run_id", "tick", "event_time", "arrival_time", "server_id", "rack_id",
            "class_id", "version", "exposure", "request_count", "latency_ms",
            "memory_mb", "cpu_fraction", "error_count", "observed"
        ]
        with open(out_path / "telemetry.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=telem_fields, extrasaction="ignore")
            w.writeheader()
            for r in all_telemetry:
                w.writerow(r.to_dict())

    return ScenarioRunResult(
        scenario_name=scenario.name,
        manifest=manifest_dict,
        telemetry=all_telemetry,
        model_policy=model_policy,
        recommendations=recommendations,
        evaluator_results=evaluator_results,
        output_dir=out_path,
    )
