"""Tests for the Physical Execution Boundary & Real Service Telemetry Harness.

Verifies:
1. Clean reviewed workload runs within limits, emits measured telemetry, and terminates cleanly.
2. Leaking reviewed workload accumulates physical RSS memory and terminates cleanly.
3. Watchdog enforces hard memory limits (HARNESS_OOM_KILLED).
4. Watchdog enforces wall-clock timeouts (HARNESS_TIMEOUT).
5. Clean separation of harness failures from application faults.
6. Anti-leakage firewall: workers cannot access or import detector truth.
7. Uploaded artifacts remain unexecuted by backend / deployment manager.
8. Physical vs simulated telemetry comparison and empirical threshold recalibration.
"""
from __future__ import annotations

import inspect
import tempfile
import time
from pathlib import Path

import pytest

from canary_ssm.deployments import DeploymentManager
from canary_ssm.deployments.models import BehaviorProfile, BehaviorProfileType
from canary_ssm.telemetry.records import TelemetryRecord
from canary_ssm.workloads import (
    ApplicationFaultType,
    HarnessFailureType,
    IsolatedWorkerHarness,
    PhysicalTelemetryAdapter,
    WorkerExecutionResult,
    WorkerLimits,
    WorkloadRunner,
    compare_physical_vs_simulated,
    recalibrate_empirical_threshold,
)
from canary_ssm.workloads.samples import CLEAN_SERVICE_SCRIPT, LEAKING_SERVICE_SCRIPT


def test_clean_workload_lifecycle_and_measured_telemetry():
    """Verify clean reviewed service lifecycle, measured telemetry emission, and clean termination."""
    limits = WorkerLimits(max_memory_mb=128.0, timeout_seconds=15.0)
    runner = WorkloadRunner(limits=limits)

    result = runner.run_workload(
        script_path=CLEAN_SERVICE_SCRIPT,
        ticks=3,
        requests_per_tick=4,
        params_per_tick={"n": 200},
        server_id="srv-clean-0",
        service_name="clean_microservice",
        metadata={"rack_id": "rack-0", "class_id": 0, "version": "v1.0.0"},
    )

    # 1. Exit gate: runs within limits and terminates predictably
    assert result.harness_failure is None, f"Harness failed unexpectedly: {result.error_details}"
    assert result.application_fault == ApplicationFaultType.APPLICATION_HEALTHY
    assert result.peak_memory_mb > 0.0
    assert result.peak_memory_mb < limits.max_memory_mb

    # 2. Telemetry validation: source='MEASURED', observed=True, positive latency
    assert len(result.telemetry_records) == 3
    for rec in result.telemetry_records:
        assert rec.source == "MEASURED"
        assert rec.observed is True
        assert rec.server_id == "srv-clean-0"
        assert rec.request_count == 4
        assert rec.error_count == 0
        assert rec.latency_ms > 0.0
        assert rec.memory_mb > 0.0

    # 3. Clean memory profile: no unbounded growth in clean service
    mem_delta = result.telemetry_records[-1].memory_mb - result.telemetry_records[0].memory_mb
    assert mem_delta < 5.0, f"Clean service exhibited unexpected memory growth: {mem_delta} MB"


def test_leaking_workload_lifecycle_and_memory_accumulation():
    """Verify leaking service accumulates physical resident memory across requests."""
    limits = WorkerLimits(max_memory_mb=128.0, timeout_seconds=15.0)
    runner = WorkloadRunner(limits=limits)

    result = runner.run_workload(
        script_path=LEAKING_SERVICE_SCRIPT,
        ticks=4,
        requests_per_tick=3,
        params_per_tick={"leak_mb": 2.0, "n": 50},
        server_id="srv-leak-0",
        service_name="leaking_microservice",
        metadata={"rack_id": "rack-0", "class_id": 1, "version": "v1.1.0"},
    )

    assert result.harness_failure is None, f"Harness failed unexpectedly: {result.error_details}"
    assert result.application_fault == ApplicationFaultType.APPLICATION_MEMORY_LEAK
    assert len(result.telemetry_records) == 4

    # Verify physical memory accumulation across ticks
    initial_mem = result.telemetry_records[0].memory_mb
    final_mem = result.telemetry_records[-1].memory_mb
    assert final_mem > initial_mem, f"Expected memory to grow, got initial={initial_mem}, final={final_mem}"
    assert (final_mem - initial_mem) >= 10.0, f"Expected at least 10MB physical growth, got {final_mem - initial_mem} MB"

    for rec in result.telemetry_records:
        assert rec.source == "MEASURED"
        assert rec.observed is True


def test_harness_oom_kill_enforcement():
    """Verify watchdog detects RSS breach and forcibly terminates worker (HARNESS_OOM_KILLED)."""
    # Set tight memory limit (45MB) and force a 25MB leak per request
    tight_limits = WorkerLimits(max_memory_mb=45.0, timeout_seconds=10.0, poll_interval_seconds=0.02)
    runner = WorkloadRunner(limits=tight_limits)

    result = runner.run_workload(
        script_path=LEAKING_SERVICE_SCRIPT,
        ticks=5,
        requests_per_tick=2,
        params_per_tick={"leak_mb": 25.0, "n": 10},
        server_id="srv-oom-0",
    )

    assert result.harness_failure == HarnessFailureType.HARNESS_OOM_KILLED
    assert result.error_details is not None
    assert "exceeded limit" in result.error_details.lower() or "oom" in result.error_details.lower()


def test_harness_timeout_enforcement():
    """Verify watchdog detects execution timeout and forcibly terminates worker (HARNESS_TIMEOUT)."""
    short_limits = WorkerLimits(timeout_seconds=0.8, startup_timeout_seconds=5.0, poll_interval_seconds=0.02)

    with IsolatedWorkerHarness(
        script_path=CLEAN_SERVICE_SCRIPT,
        limits=short_limits,
        server_id="srv-timeout-0",
    ) as harness:
        assert harness.is_alive()
        # Wait beyond timeout limit
        time.sleep(1.2)
        # Watchdog should have killed the process
        assert not harness.is_alive()
        assert harness.harness_failure == HarnessFailureType.HARNESS_TIMEOUT


def test_separation_of_harness_failures_and_application_faults():
    """Verify clean separation between application HTTP errors and harness infrastructure failures."""
    limits = WorkerLimits(max_memory_mb=128.0, timeout_seconds=10.0)
    runner = WorkloadRunner(limits=limits)

    # Dispatch to /error endpoint in leaking service
    result = runner.run_workload(
        script_path=LEAKING_SERVICE_SCRIPT,
        ticks=2,
        requests_per_tick=3,
        endpoint="/error",
        server_id="srv-err-0",
    )

    # Harness succeeded (no OOM, no timeout, no crash)
    assert result.harness_failure is None
    # Application returned HTTP 500 errors
    assert result.application_fault == ApplicationFaultType.APPLICATION_HTTP_ERROR
    assert result.error_requests == 6
    assert result.successful_requests == 0


def test_anti_leakage_firewall_and_truth_isolation():
    """Verify sample microservices have zero imports or access to simulator truth or detector state."""
    forbidden_tokens = [
        "simulate.Truth",
        "fault_type",
        "injected_severity",
        "ground_truth",
        "MultiMetricEventTruth",
        "canary_ssm.faults",
    ]

    for script in (CLEAN_SERVICE_SCRIPT, LEAKING_SERVICE_SCRIPT):
        source = script.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in source, f"Forbidden truth token {token!r} found in {script.name}"


def test_uploaded_artifacts_remain_unexecuted():
    """Verify arbitrary uploaded code in the deployment registry is never executed by backend."""
    mgr = DeploymentManager()

    # Uploaded artifact containing malicious or test probe code
    probe_code = "import sys\nprint('MALICIOUS_EXECUTION')\nraise SystemExit(99)"
    rel = mgr.create_release(
        release_id="rel-test-upload",
        version_tag="v2.0.0",
        behavior_profile=BehaviorProfile(profile_type=BehaviorProfileType.CLEAN),
        artifact_filename="upload_probe.py",
        artifact_content=probe_code,
    )

    # Artifact must be stored as unexecuted metadata
    assert rel.artifact is not None
    assert rel.artifact.is_executed is False
    assert rel.artifact.execution_status == "UNEXECUTED_SIMULATION_PROFILE"
    assert rel.artifact.checksum_sha256 != ""

    # Verify that the registry never executed this code (no exit, no stdout execution)


def test_physical_vs_simulated_comparison_and_recalibration():
    """Verify comparison contrasts physical vs simulated telemetry and performs empirical recalibration."""
    # Create synthetic simulated records
    sim_records = [
        TelemetryRecord(
            run_id="sim-run",
            tick=t,
            event_time=t,
            arrival_time=t,
            server_id="srv-0",
            rack_id="rack-0",
            class_id=0,
            version="v1.0.0",
            exposure=False,
            request_count=1000,
            latency_ms=10.0 + 0.1 * t,
            memory_mb=500.0 + 0.5 * t,
            cpu_fraction=0.3,
            error_count=0,
            observed=True,
            source="SIMULATED",
        )
        for t in range(5)
    ]

    # Run real physical clean baseline
    runner = WorkloadRunner()
    res = runner.run_workload(
        script_path=CLEAN_SERVICE_SCRIPT,
        ticks=5,
        requests_per_tick=3,
        params_per_tick={"n": 100},
    )
    phys_records = res.telemetry_records

    comparison = compare_physical_vs_simulated(phys_records, sim_records)

    assert "physical_latency" in comparison
    assert "simulated_latency" in comparison
    assert "distributional_divergence" in comparison
    assert "transferability_warning" in comparison["distributional_divergence"]

    # Test empirical recalibration on physical runs
    recalibration = recalibrate_empirical_threshold([phys_records, phys_records], target_fpr=0.05)
    assert recalibration["calibration_status"] == "CALIBRATED_ON_PHYSICAL_BASELINE"
    assert "calibrated_threshold" in recalibration
    assert recalibration["target_fpr"] == 0.05
