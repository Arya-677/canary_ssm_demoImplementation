"""Unit and Integration Tests for DetectorService (Prompt 10).

Verifies:
1. Complete Firewall: No imports of simulate.Truth, metrics, or truth files.
2. Causality: Streaming ingestion and baseline fitting strictly on pre-period data.
3. Latency & Memory Evidence: Host effect intervals, class effects, host risk, memory drift, headroom, TTE.
4. Infrastructure vs Release Separation: Rack degradation reported as RACK_DEGRADED while release remains RUNNING.
5. Identifiability Guard: Missing rack controls forces INSUFFICIENT DATA / CONFLICT without release inference.
6. Frozen Policy Alerting: Latency and memory breaches trigger PAUSE RECOMMENDED with first alert timestamp.
7. Disconnection Fallback: Toggling ssm_connected returns DETECTOR NOT CONNECTED while data remains accessible.
8. Automated Rollback: Opt-in mode records intervention tick and marks censored.
"""
from __future__ import annotations

import math
import numpy as np
import pytest

from canary_ssm.detector_service import (
    ClassEvidence,
    DetectorService,
    DetectorTickResult,
    FrozenPolicy,
    HostEvidence,
)
from canary_ssm.telemetry.records import TelemetryRecord


def _make_server_metadata() -> dict[str, dict]:
    """Create metadata for 4 racks x 6 servers = 24 servers."""
    meta = {}
    for r in range(4):
        for s in range(6):
            sid = f"srv-r{r}-s{s}"
            cls_id = 0 if s < 3 else 1
            meta[sid] = {
                "server_id": sid,
                "rack_id": f"rack-{r}",
                "class_id": cls_id,
                "memory_capacity_mb": 16384.0,
                "base_latency_ms": 100.0,
            }
    return meta


def _generate_telemetry_tick(
    tick: int,
    servers: list[str],
    meta: dict[str, dict],
    canary_ids: list[str] = (),
    lat_shift: float = 0.0,
    mem_growth_mb: float = 0.0,
    rack_shock: dict[str, float] | None = None,
    drop_rack_controls: str | None = None,
) -> list[TelemetryRecord]:
    """Generate deterministic synthetic telemetry records for a tick."""
    records = []
    rack_shock = rack_shock or {}

    for sid in servers:
        m = meta[sid]
        rk = m["rack_id"]
        cls_id = m["class_id"]
        is_canary = sid in canary_ids

        # If drop_rack_controls is set, omit control records for that rack
        if drop_rack_controls and rk == drop_rack_controls and not is_canary:
            continue

        # Base latency with rack shock and canary shift
        base_lat = m["base_latency_ms"]
        shock = rack_shock.get(rk, 0.0)
        c_shift = lat_shift if is_canary else 0.0
        lat_ms = base_lat * math.exp(shock + c_shift)

        # Base memory with canary growth
        base_mem = 2048.0
        c_mem = (mem_growth_mb * max(0, tick - 20)) if is_canary else 0.0
        mem_mb = base_mem + c_mem

        rec = TelemetryRecord(
            run_id="run-test",
            tick=tick,
            event_time=tick,
            arrival_time=tick,
            server_id=sid,
            rack_id=rk,
            class_id=cls_id,
            version="v1.1.0" if is_canary else "v1.0.0",
            exposure=is_canary,
            request_count=1000,
            latency_ms=lat_ms,
            memory_mb=mem_mb,
            cpu_fraction=0.45,
            error_count=0,
            observed=True,
        )
        records.append(rec)
    return records


class TestDetectorService:
    """Test suite verifying DetectorService correctness and safety rules."""

    def test_firewall_rule_no_truth_imports(self):
        """Rule 1: Detector service must NEVER import simulate.Truth, metrics, or read truth files."""
        import ast
        import inspect
        import canary_ssm.detector_service as mod

        source = inspect.getsource(mod)
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "Truth" not in alias.name
                    assert "metrics" not in alias.name
                    assert "_truth" not in alias.name
            elif isinstance(node, ast.ImportFrom):
                mod_name = node.module or ""
                assert "metrics" not in mod_name
                assert "_truth" not in mod_name
                for alias in node.names:
                    assert alias.name != "Truth"
                    assert "metrics" not in alias.name
                    assert "_truth" not in alias.name

    def test_preperiod_fitting_and_null_operation(self):
        """Verify healthy pre-period baseline fitting and nominal RUNNING advisory."""
        meta = _make_server_metadata()
        servers = list(meta.keys())
        service = DetectorService(expected_servers=servers, server_metadata=meta)

        # Ingest 25 pre-period ticks
        for t in range(25):
            recs = _generate_telemetry_tick(t, servers, meta)
            service.ingest(recs)
            res = service.step(t)
            assert res.infrastructure_advisory == "NORMAL"
            assert res.canary_release_advisory == "RUNNING"
            assert res.attribution == "NORMAL"

        assert service.slice_builder.baseline is not None
        assert len(service.history) == 25

    def test_latency_regression_evidence_and_credible_intervals(self):
        """Verify host effect estimates, 95% CIs, class effects, and host harm risks."""
        meta = _make_server_metadata()
        servers = list(meta.keys())
        canaries = ["srv-r0-s0", "srv-r1-s0", "srv-r2-s0", "srv-r3-s0"]
        service = DetectorService(expected_servers=servers, server_metadata=meta)

        # 25 pre-period baseline ticks
        for t in range(25):
            service.ingest(_generate_telemetry_tick(t, servers, meta))
            service.step(t)

        # Deploy canary at t=25
        service.set_deployment(release_id="rel-v1.1-lat", canary_ids=canaries, t0=25)

        # Post-period with +15% latency regression on canaries
        for t in range(25, 35):
            recs = _generate_telemetry_tick(t, servers, meta, canary_ids=canaries, lat_shift=0.15)
            service.ingest(recs)
            res = service.step(t)

        # Verify evidence outputs
        evidence = service.get_evidence()
        assert len(evidence["class_effects"]) > 0
        assert len(evidence["servers"]) == len(servers)

        for cid in canaries:
            h = evidence["servers"][cid]
            assert h["role"] == "CANARY"
            assert h["latency_effect"] is not None
            assert h["latency_se"] is not None and h["latency_se"] > 0
            assert h["latency_ci_lower"] < h["latency_effect"] < h["latency_ci_upper"]
            assert 0.0 <= h["host_risk"] <= 1.0

        status = service.get_status()
        assert status["model_id"] == "MODEL-HSSM-V1"
        assert status["policy_id"] == "POLICY-SIDAK-0.05"
        assert status["canary_release_advisory"] == "PAUSE RECOMMENDED"
        assert "Elevated latency contrast" in status["advisory_reason"]
        assert "not proof of a code bug" in status["epistemic_disclaimer"]

    def test_memory_growth_and_capacity_guardrail(self):
        """Verify memory channel drift detection, persistence gating, and headroom/TTE."""
        meta = _make_server_metadata()
        servers = list(meta.keys())
        canaries = ["srv-r0-s0", "srv-r1-s0", "srv-r2-s0", "srv-r3-s0"]
        service = DetectorService(expected_servers=servers, server_metadata=meta)

        for t in range(20):
            service.ingest(_generate_telemetry_tick(t, servers, meta))
            service.step(t)

        service.set_deployment(release_id="rel-v1.2-leak", canary_ids=canaries, t0=20)

        # +30 MB/min memory growth for 20 ticks (exceeds 15 min persistence window)
        for t in range(20, 42):
            recs = _generate_telemetry_tick(t, servers, meta, canary_ids=canaries, mem_growth_mb=30.0)
            service.ingest(recs)
            res = service.step(t)

        latest = service.history[-1]
        assert latest.score_mem is not None
        assert latest.score_mem > service.frozen_policy.threshold_mem
        assert latest.canary_release_advisory == "PAUSE RECOMMENDED"
        assert latest.attribution in ("MEMORY_GROWTH_LEAK", "COMPOUND_REGRESSION")

        for cid in canaries:
            h = latest.hosts[cid]
            assert h.memory_drift_mb_per_min is not None and h.memory_drift_mb_per_min > 5.0
            assert h.headroom_mb is not None and h.headroom_mb < 16384.0
            assert h.is_persistent_mem is True

    def test_infrastructure_vs_release_advisory_separation(self):
        """Verify rack degradation is attributed to infrastructure while release remains RUNNING."""
        meta = _make_server_metadata()
        servers = list(meta.keys())
        canaries = ["srv-r0-s0", "srv-r1-s0", "srv-r2-s0", "srv-r3-s0"]
        service = DetectorService(expected_servers=servers, server_metadata=meta)

        for t in range(25):
            service.ingest(_generate_telemetry_tick(t, servers, meta))
            service.step(t)

        service.set_deployment(release_id="rel-v1.0-clean", canary_ids=canaries, t0=25)

        # Inject +20% rack shock on rack-0 (both canaries and controls experience it)
        # Release itself is CLEAN (lat_shift = 0.0)
        for t in range(25, 32):
            recs = _generate_telemetry_tick(
                t, servers, meta,
                canary_ids=canaries,
                lat_shift=0.0,
                rack_shock={"rack-0": 0.20},
            )
            service.ingest(recs)
            res = service.step(t)

        # Infrastructure advisory detects rack slowdown
        assert "RACK_DEGRADED: rack-0" in res.infrastructure_advisory or "rack-0" in res.infrastructure_advisory
        # Because same-rack controls absorbed the shock, release advisory remains RUNNING!
        assert res.canary_release_advisory == "RUNNING"
        assert res.attribution == "NORMAL"

    def test_identifiability_guard_missing_rack_controls(self):
        """Verify that missing rack controls blocks release cause attribution."""
        meta = _make_server_metadata()
        servers = list(meta.keys())
        canaries = ["srv-r0-s0", "srv-r1-s0", "srv-r2-s0", "srv-r3-s0"]
        service = DetectorService(expected_servers=servers, server_metadata=meta)

        for t in range(25):
            service.ingest(_generate_telemetry_tick(t, servers, meta))
            service.step(t)

        service.set_deployment(release_id="rel-confounded", canary_ids=canaries, t0=25)

        # Drop all baseline controls in rack-0
        for t in range(25, 28):
            recs = _generate_telemetry_tick(
                t, servers, meta,
                canary_ids=canaries,
                drop_rack_controls="rack-0",
            )
            service.ingest(recs)
            res = service.step(t)

        assert res.is_unidentifiable is True
        assert res.canary_release_advisory == "INSUFFICIENT DATA / CONFLICT"
        assert res.attribution == "INSUFFICIENT_DATA"
        assert "IDENTIFIABILITY_GUARD" in res.advisory_reason

    def test_disconnection_fallback(self):
        """Verify that disconnecting SSM returns DETECTOR NOT CONNECTED without losing telemetry."""
        meta = _make_server_metadata()
        servers = list(meta.keys())
        service = DetectorService(expected_servers=servers, server_metadata=meta)

        for t in range(10):
            service.ingest(_generate_telemetry_tick(t, servers, meta))
            service.step(t)

        # Disconnect detector
        service.set_ssm_connected(False)
        status = service.get_status()

        assert status["ssm_connected"] is False
        assert status["canary_release_advisory"] == "DETECTOR NOT CONNECTED"
        assert status["release_score"] is None
        assert "DETECTOR NOT CONNECTED" in status["advisory_reason"]

        # Telemetry and timeline history remain intact
        timeline = service.get_timeline(limit=10)
        assert len(timeline) == 10
        assert timeline[-1]["control_latency_mean"] > 0

    def test_automated_rollback_opt_in(self):
        """Verify opt-in automated rollback intervention logging."""
        meta = _make_server_metadata()
        servers = list(meta.keys())
        canaries = ["srv-r0-s0", "srv-r1-s0", "srv-r2-s0", "srv-r3-s0"]
        service = DetectorService(
            expected_servers=servers,
            server_metadata=meta,
            enable_auto_rollback=True,
        )

        for t in range(25):
            service.ingest(_generate_telemetry_tick(t, servers, meta))
            service.step(t)

        service.set_deployment(release_id="rel-v1.1-lat", canary_ids=canaries, t0=25)

        # Severe latency regression triggering alert
        for t in range(25, 32):
            recs = _generate_telemetry_tick(t, servers, meta, canary_ids=canaries, lat_shift=0.30)
            service.ingest(recs)
            res = service.step(t)
            if res.auto_rollback_triggered:
                break

        latest = service.history[-1]
        assert latest.auto_rollback_triggered is True
        assert latest.intervention_tick is not None
        assert latest.censored is True
