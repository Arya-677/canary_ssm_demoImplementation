# Canary SSM Dashboard: First-Time User Guide

Welcome to the **Canary SSM (Hierarchical State-Space Modeling) Interactive Virtual Data Center**. This guide provides step-by-step instructions for running, inspecting, and understanding canary deployment experiments using the web dashboard.

---

## 1. Quick Start (1 Command to Launch)

Launch the dashboard from your terminal:

```bash
python -m canary_ssm.cli dashboard --host 127.0.0.1 --port 8000
```
or via the installed console entry point:
```bash
canary-ssm dashboard --port 8000
```

Open your browser to:
[http://127.0.0.1:8000](http://127.0.0.1:8000)

---

## 2. One-Click Demo Mode

When the dashboard opens, you are immediately greeted by the **Interactive Quick-Start Header** at the top of the screen:

1. **Preset Selector:** Choose from 8 canonical benchmark scenarios:
   - `Clean Release (Null)`: A clean software release with zero regression. Verifies false-alert control ($\le 5\%$).
   - `Release Leak on 2 Canaries`: A genuine memory leak regression (+35 MB/min) on 2 canary servers.
   - `Rack Slowdown (Confounded)`: A severe physical switch failure on Rack 0 affecting both canaries and controls.
   - `Fleet Demand Spike`: A diurnal load shock that tests demand invariance.
   - `CPU Regression`: Spinlock contention regression (+35% CPU).
   - `Healthy GC Oscillations`: Sawtooth allocation/sweep cycles (tests that healthy memory churn is not labeled a leak).
   - `Combined Rack + Leak`: Simultaneous physical infrastructure degradation and release harm.
   - `Missing Controls (Unidentifiable)`: Deliberate bad allocation where canaries occupy an entire rack without concurrent controls.
2. **Click "▶ Start Demo":** The system automatically loads the selected scenario, resets the simulator seed, applies pre-conditions, and begins streaming live telemetry into the **Monitoring** tab.

---

## 3. The 7-Step Experiment Workflow

The dashboard organizes canary monitoring into 7 self-contained steps:

```
[1. Select Scenario] ➔ [2. Register Release] ➔ [3. Deploy Canary] ➔ [4. Stream Telemetry]
                                                                          │
[7. Ground Truth Audit]  [6. Compare Pooling]  [5. SSM Evidence] ─────┘
```

### Step 1: Select Scenario Preset (`Overview` Tab)
- Review the datacenter topology: 4 Datacenter Racks (`RACK-0` through `RACK-3`), 24 Physical Servers (`srv-r0-s0` to `srv-r3-s5`), and 2 Hardware Classes (`Class 0` and `Class 1`).
- Inspect pre-period warmup duration (typically 45 minutes) and evaluation horizon (75 minutes).

### Step 2: Register Versioned Release (`Releases` Tab)
- Create or inspect a release artifact (e.g., `rel-v1.2-leak`).
- Each artifact records a cryptographic **SHA-256 checksum** and is explicitly labeled **`UNEXECUTED`**.
- *Security Guarantee:* The simulator and detector evaluate behavioral models and measured telemetry; arbitrary code files remain strictly unexecuted in dashboard and detector processes.

### Step 3: Deploy Canary & Validate Allocation (`Releases` Tab)
- Select canary target servers across racks and classes.
- **Identifiability Guard:** Click **Validate Allocation**. The system enforces that every rack and hardware class containing a canary host must also have at least one unexposed baseline control host.
- Pure-canary racks or pure-canary classes are strictly rejected as **`UNIDENTIFIABLE`** because infrastructure confounders cannot be causally separated from release effects without concurrent controls.

### Step 4: Stream Real-Time Telemetry (`Monitoring` Tab)
- Monitor real-time charts comparing **Canary (Purple)** against **Baseline Control (Blue)** series:
  - **Latency (ms):** Raw request response time.
  - **Memory (MB):** Process resident set size with capacity thresholds.
  - **CPU Utilization (%):** Core saturation.
  - **Error Counts:** Request failure rate.
- Observe how shared shocks (such as fleet demand spikes or rack switch slowdowns) affect both purple and blue lines simultaneously, allowing the detector to eliminate them.

### Step 5: Examine SSM Evidence (`SSM Evidence` Tab)
- View host-level state-space estimates:
  - **Latency Effect ($\hat{a}_i$):** State-space estimated log effect.
  - **95% Credible Interval:** Filtered uncertainty bounds $[\hat{a}_i - 1.96 \cdot \text{SE}, \hat{a}_i + 1.96 \cdot \text{SE}]$.
  - **Percentage Shift (%):** Intuitive transformed percentage increase in latency ($100 \times (\exp(\hat{a}_i) - 1)$).
  - **Host Risk $P(a_i > \log(1.02))$:** Posterior probability that the host suffers a latency increase exceeding the $+2.0\%$ operational harm boundary.
  - **Release Score ($\max_i \log P$):** Fleet-wide decision metric.
  - **Memory Drift Rate:** Fitted slope in MB/min.
  - **Headroom & TTE:** Remaining RAM capacity and estimated time-to-exhaustion in minutes.
- **Within-Class Shrinkage:** Inspect the Class Effects breakdown ($\theta_g$). Hosts within the same hardware class shrink toward their class mean via Helmert contrast matrices, damping random host noise while preserving sensitivity to genuine regression.

### Step 6: Side-by-Side Method Comparison (`Method Comparison` Tab)
Compare 3 state-space pooling paradigms running concurrently on the live stream:
1. **Hierarchical SSM (Partial Pooling - Recommended):**
   - Shrinks host estimates toward their hardware class mean using Helmert orthonormal contrast matrices ($B^T B = I_{n-G}$, $C^T B = 0$).
   - Combines statistical power across hosts while maintaining host-level specificity.
2. **Independent SSM (No Pooling - Baseline):**
   - Estimates each canary host in complete isolation.
   - Suffers from high estimation variance on small samples and slower alert times.
3. **Complete Pooling SSM:**
   - Forces all canary hosts to share a single common effect parameter.
   - High power when harm is uniform across all canaries, but completely washes out regressions isolated to a single host.

### Step 7: Ground Truth Audit (`Evaluation` Tab)
- **Evaluator Truth Firewall:** Verifies the detector's recommendation against hidden simulation truth.
- View real-time confusion classification:
  - **Correct Release (True Negative):** Clean release allowed to proceed.
  - **Correct Pause (True Positive):** Faulty release paused early.
  - **False Alarm (Type I Error):** Clean release paused erroneously.
  - **Missed Regression (Type II Error):** Faulty release allowed to proceed.
- Inspect the **Gate G2 Validity Audit Table** comparing empirical false alert rates against the exact Beta-Binomial validity threshold.

---

## 4. Key Concepts & Mathematical Definitions

### Release Score: Maximum Host Risk
The fleet release decision is based on:
$$\text{Score}_t = \max_{i \in \text{Canaries}} \log P(a_{it} > \kappa_{\text{lat}} \mid \text{data}_{\le t})$$

- **Harm Boundary:** $\kappa_{\text{lat}} = \log(1.02) \approx +0.0198$ represents an operational $+2.0\%$ latency regression.
- **Scale:** The release score is on a **log-probability scale** in $(-\infty, 0.0]$.
  - $\log(0.50) \approx -0.693$: $50\%$ posterior probability of regression.
  - $\log(0.95) \approx -0.051$: $95\%$ posterior probability of regression.
  - $\log(0.01) \approx -4.605$: $1\%$ posterior probability of regression.

### Dual Advisory Architecture
To avoid falsely blaming a software deployment for network or hardware outages:
1. **`InfrastructureAdvisory`:** Evaluates concurrent baseline controls across all racks. If a rack's switch fails, the advisory displays `RACK_DEGRADED (Rack 0)` or `FLEET_OUTAGE`.
2. **`CanaryReleaseAdvisory`:** Evaluates canary-specific effect shifts after removing rack and fleet nuisance factors. Displays `NORMAL`, `PAUSE RECOMMENDED`, or `ROLLED BACK`.

When controls are missing or confounded, the system refuses to guess and reports:
`CANARY RELEASE ADVISORY: INSUFFICIENT DATA (Confounded / Absent Controls)`.

---

## 5. System States & Honest Transparency

The dashboard status pill reflects an 8-state machine:
- `WAITING_FOR_DATA`: Initial state before observations arrive (displays neutral gray, never green NORMAL).
- `INSUFFICIENT_DATA`: Telemetry stream lacks required pre-period observations.
- `MONITORING`: Active state with real-time state-space inference.
- `STALE_DATA`: Simulation paused or telemetry delayed beyond freshness threshold.
- `CONNECTION_ERROR`: Detector service disconnected from telemetry stream.
- `COMPLETED_REPLAY`: Historical run replay completed.
- `PAUSED_MONITORING`: World paused by operator.
- `UNCALIBRATED_POLICY`: Exploratory run using unvalidated threshold defaults.

### Calibration Audit & Known Limitations
- **Gate G2 Passed:** Hierarchical SSM with factor subtraction passes the exact Beta-Binomial validity test ($B \ge 2000, n \ge 2000$) across stationary nulls, step-contaminated nulls, and heavy-tailed disturbances.
- **Known Failure Under S5 (Label Errors):** In `results/x04/x04_summary.md`, `hier_rank0` (which omits nested SVD factor subtraction) failed Gate G2 under label noise ($p = 1.218 \times 10^{-8}$). The dashboard explicitly flags `hier_rank0` on S5 as **INVALIDATED**.
- **Deferred Scope:** Borg cluster traces and neural/Mamba/LSTM baselines were designated as deferred research scope in `docs/DESIGN_DECISIONS.md`. Observational telemetry isolates statistical evidence of abnormal growth, not mathematical proof of source code bugs.
