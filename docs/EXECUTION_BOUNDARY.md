# Physical Execution Boundary & Real Service Telemetry Specification

## 1. Executive Summary & Design Rationale
The core **Canary SSM Virtual Data Center** operates as a high-fidelity numerical simulator (Prompts 1–9), modeling fleet latency, process memory, and rack confounders through coupled discrete state-space and autoregressive equations. In that simulator, software versions and behavior profiles are parameterized mathematically; uploaded artifacts are explicitly labeled `UNEXECUTED_SIMULATION_PROFILE` and hashed for provenance tracking without host execution.

This extension introduces a **Physical Execution Boundary** to safely run reviewed microservices in real operating system processes, measuring actual resident memory (RSS via `psutil`), real HTTP round-trip latency, and actual error rates through the same `TelemetryRecord` adapter contract (`source="MEASURED"`).

---

## 2. Execution Boundary Architecture & Environment

```
+------------------------------------------------------------------------------------+
|                               HOST RUNTIME ENVIRONMENT                             |
|  +--------------------------------+       +-------------------------------------+  |
|  |     FastAPI / Dashboard        |       |        Detector Service / SSM       |  |
|  |  (Arbitrary uploads stored     |       |   (Consumes TelemetryRecords only;  |  |
|  |   as SHA-256 metadata blobs;   |       |    has ZERO access to truth or      |  |
|  |   NEVER executed on host)      |       |    service process memory)          |  |
|  +--------------------------------+       +-------------------------------------+  |
|                  |                                           ^                     |
|                  | (Invokes only reviewed code)              |                     |
|                  v                                           |                     |
|  +-------------------------------------------------------------------------------+  |
|  |                        WORKLOAD RUNNER & TELEMETRY ADAPTER                    |  |
|  |  - Dispatches discrete request batches per simulation tick                     |  |
|  |  - Queries psutil for physical process RSS and CPU utilization                 |  |
|  |  - Measures high-resolution HTTP response latency (perf_counter)               |  |
|  |  - Emits TelemetryRecord(source="MEASURED", observed=True)                     |  |
|  +-------------------------------------------------------------------------------+  |
|                  |                                           ^                     |
|                  v                                           | (HTTP / Metrics)    |
|  +-------------------------------------------------------------------------------+  |
|  |                  DISPOSABLE ISOLATED WORKER HARNESS                           |  |
|  |  +-------------------------------------------------------------------------+  |  |
|  |  |  Process Boundary:                                                      |  |  |
|  |  |  - Dedicated OS process group (CREATE_NEW_PROCESS_GROUP on Windows)     |  |  |
|  |  |  - Ephemeral scratch directory (tempfile.TemporaryDirectory)          |  |  |
|  |  |  - Sanitized environment (zero truth tokens or leaking paths)           |  |  |
|  |  |  - Network bound strictly to loopback (127.0.0.1) on dynamic port 0    |  |  |
|  |  +-------------------------------------------------------------------------+  |  |
|  |  |  Resource Watchdog (Background Thread):                                 |  |  |
|  |  |  - Hard RSS Memory Limit (e.g. 128 MB cap) -> HARNESS_OOM_KILLED         |  |  |
|  |  |  - Wall-clock Execution Timeout (e.g. 30s) -> HARNESS_TIMEOUT           |  |  |
|  |  |  - Startup Readiness Probe (/health)     -> HARNESS_STARTUP_FAILURE     |  |  |
|  |  +-------------------------------------------------------------------------+  |  |
|  |  |  Teardown Protocol:                                                     |  |  |
|  |  |  - Graceful /shutdown -> Recursive child process kill via psutil ->    |  |  |
|  |  |    process.kill() -> Directory cleanup (zero zombie processes)          |  |  |
|  |  +-------------------------------------------------------------------------+  |  |
|  |                                                                               |  |
|  |  Target Microservice:                                                         |  |
|  |  - Reviewed Clean Service (clean_service.py) OR                               |  |
|  |  - Reviewed Leaking Service (leaking_service.py)                              |  |
|  +-------------------------------------------------------------------------------+  |
+------------------------------------------------------------------------------------+
```

### 2.1 Environmental Requirements
- **OS Support**: Windows (PowerShell / `CREATE_NEW_PROCESS_GROUP`) and Unix/Linux (`os.setsid`).
- **Runtime**: Python 3.10+ (current system: Python 3.15.0).
- **Core Dependencies**: `psutil` (for process RSS, CPU, and child process harvesting), standard library `subprocess`, `tempfile`, `urllib.request`, `http.server`, `threading`, `socket`.
- **Network Access**: Strictly loopback (`127.0.0.1`). No external internet/WAN egress required or permitted.

### 2.2 Security & Isolation Boundaries
1. **Arbitrary Upload Protection**: Uploaded source artifacts are stored exclusively in the release registry with SHA-256 hashes and file size limits. They are **never executed** by the backend or dashboard.
2. **Restricted Mount & Execution Path**: The isolated worker harness executes only reviewed, validated sample scripts (`clean_service.py` and `leaking_service.py`) or explicitly designated runner targets.
3. **Process Group Isolation**: Workers run in dedicated process groups so that forced termination reaps all subprocesses without leaving orphans.
4. **Ephemeral Filesystem**: Workers run inside disposable temporary directories (`tempfile.TemporaryDirectory`) that are destroyed upon worker teardown.
5. **Anti-Leakage Firewall**: Worker scripts contain zero imports or references to `canary_ssm.faults.truth`, `simulate.Truth`, or evaluator metrics.

---

## 3. Failure Taxonomy: Harness vs Application Faults

To prevent confounding test infrastructure failures with software bugs, failures are strictly segregated into two orthogonal categories:

| Category | Type | Root Cause / Trigger | Consequence |
| :--- | :--- | :--- | :--- |
| **Harness Failure** | `HARNESS_OOM_KILLED` | Worker RSS memory exceeded `limits.max_memory_mb` | Watchdog forcibly terminates worker |
| **Harness Failure** | `HARNESS_TIMEOUT` | Worker wall-clock time exceeded `limits.timeout_seconds` | Watchdog forcibly terminates worker |
| **Harness Failure** | `HARNESS_STARTUP_FAILURE` | Worker failed to bind port or answer `/health` probe | Harness aborts before running workload |
| **Harness Failure** | `HARNESS_CRASH` | Subprocess exited unexpectedly with non-zero exit code | Harness records crash details |
| **Application Fault**| `APPLICATION_HEALTHY` | Worker serviced traffic within limits without errors | Normal healthy operation |
| **Application Fault**| `APPLICATION_MEMORY_LEAK` | Worker accumulated physical memory persistently across requests | Software memory leak regression |
| **Application Fault**| `APPLICATION_HTTP_ERROR` | Worker returned HTTP 5xx errors or dropped requests | Software service regression |
| **Application Fault**| `APPLICATION_LATENCY_SPIKE` | Worker response time breached latency SLA | Performance regression |

---

## 4. Telemetry Contract & Observation Labeling

The `PhysicalTelemetryAdapter` queries the live worker process and wraps physical measurements into the standard `TelemetryRecord` dataclass:
- `latency_ms`: Geometric mean of high-resolution HTTP response round-trip latencies over the tick.
- `memory_mb`: Process Resident Set Size (RSS) in megabytes measured via `psutil.Process.memory_info().rss`.
- `cpu_fraction`: Process CPU utilization fraction $[0.0, 1.0]$ via `psutil.Process.cpu_percent()`.
- `request_count`: Total requests dispatched in the tick window.
- `error_count`: Count of non-200 responses or connection failures.
- `observed`: `True`.
- `source`: `"MEASURED"` (distinguishing physical measurements from numerical simulation `"SIMULATED"`).

---

## 5. Statistical Reality: Why Simulator Thresholds Cannot Be Blindly Transferred

### 5.1 Distributional Divergence
1. **Base Footprint**: The physical Python interpreter requires an initial baseline memory footprint (~20–30 MB RSS) for the runtime runtime heap, standard library modules, and page tables. Numerical simulations initiate from arbitrary conceptual capacities.
2. **Quantized Allocation**: Physical memory grows via discrete OS memory pages (4 KB / 2 MB huge pages) and runtime block pools (e.g. `pymalloc` arenas), producing step-wise non-linear growth rather than smooth Gaussian AR(1) drift.
3. **Latency Jitter**: Real HTTP exchanges over TCP loopback suffer OS context-switching jitter, socket buffer handshakes, and GC pause spikes, generating heavy-tailed latency distributions absent from stationary Gaussian simulation.

### 5.2 Recalibration Protocol
Because empirical residual noise variance $\hat{\sigma}^2_{\text{emp}}$ and autocorrelation $\hat{\rho}_{\text{emp}}$ differ fundamentally from numerical simulation parameters, applying simulator-calibrated decision thresholds $\tau_{\text{sim}}$ directly to physical workloads will either:
- **Inflate false alert rates** to unacceptable levels if physical noise exceeds simulation noise, or
- **Completely destroy detection sensitivity** if simulation thresholds are too conservative.

**Methodology**:
1. Run clean baseline workloads across multiple calibration seeds to gather empirical noise traces.
2. Estimate empirical residual growth variance $\hat{\sigma}^2_{\text{emp}}$ on physical baseline data.
3. Determine empirical decision threshold $\tau_{\text{emp}}$ at the declared false alert budget $\alpha$ (e.g. $\alpha = 0.05$).
4. Gate all canary release decisions on the empirical threshold.
