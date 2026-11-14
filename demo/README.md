# Canary SSM V3 — Interactive Research & Decision Demo

This directory contains the self-contained interactive demonstration for **Hierarchical, Inertia-Constrained State-Space Models for Safer Software Rollout Decisions**.

## What the Demo Shows

1. **Side-by-Side Detector Behavior:**
   - **Hierarchical SSM Filter:** Workload-adjusted Kalman filtering with posterior probability of harm $P(\text{Harm} \mid y_{1:t})$.
   - **Classical Baselines:** Standard cumulative sum (CUSUM) and raw latency contrast tracking.
2. **Preset Scenarios:**
   - `regression_recovery`: Canary regression followed by automated rollback and metric recovery.
   - `class_wide`: Class-wide correlated shock affecting both canary and control.
   - `broad_fleet`: Broad fleet shared anomaly where hierarchical smoothing decouples fleet trend from canary-specific defect.
   - `single_host_persistent`: Single-host persistent defect highlighting hierarchical shrinkage trade-offs.
   - `step_plus_harm`: Step confounder combined with genuine canary regression.
   - `iso_spike_1host`: Isolated transient spike demonstrating state-space noise rejection without false alarming.
3. **Interactive Decision Logic:**
   - Real-time hysteresis bands ($\tau_{high}$ alarm threshold and $\tau_{low}$ recovery/clear threshold).
   - Minimum persistence constraints ($k$ consecutive steps).
   - Scrubbable timeline with playback controls.

## How to Run

### Method 1: Local HTTP Server (Recommended)
Run the bundled Python server:
```bash
python demo/serve_demo.py
```
This automatically opens `http://localhost:8080/index.html` in your default browser.

To specify a custom port:
```bash
python demo/serve_demo.py --port 8888
```

### Method 2: Direct File Open
Because `demo/index.html` embeds the precomputed telemetry trajectories and relies entirely on HTML5 Canvas (no external CDN or remote JavaScript dependencies), you can also double-click `demo/index.html` or open it directly in any modern browser:
```bash
start demo/index.html
```

## Scientific Safeguards & Caveats
- **Univariate Response Only:** Calibrated for univariate service latency. Extension to multivariate systems requires joint covariance modeling.
- **Calibrated False-Alert Budget:** All decision policies are constrained to Gate G2 validity ($p \ge 0.01$).
- **Prototype Status:** This demonstration illustrates simulation research results and is not intended for unmonitored production rollout automation.
