# Demonstration Guide: Canary SSM V3 Interactive Prototype
## Operator Instructions for the Live Research Demonstration

- **Web Dashboard:** `demo/index.html` (Standalone, Zero-Dependency Offline Canvas Engine)
- **Local HTTP Server:** `demo/serve_demo.py`
- **Telemetry Dataset:** `demo/data.json`

---

### 1. Overview of the Interactive Dashboard

The interactive demonstration allows researchers, reviewers, and operators to visualize the real-time dynamics of hierarchical state-space filtering versus classical sequential baselines during software rollouts.

#### Key Dashboard Components:
1. **Scenario Preset Selector:** Loads precomputed, high-fidelity microservice telemetry across 6 representative deployment scenarios.
2. **Interactive Playback & Timeline Scrubber:** Allows playing, stepping forward, or directly scrubbing across the 120-minute simulation window with real-time decision state banners.
3. **Threshold & Hysteresis Sliders:** Real-time adjustable sliders for:
   - Alarm Threshold $\tau_{\text{high}}$ (default $0.85$, adjustable from $0.50$ to $0.99$).
   - Recovery Threshold $\tau_{\text{low}}$ (default $0.25$, adjustable from $0.05$ to $0.50$).
   - Confirmation Depth $k$ (consecutive transgressions, default $2$, adjustable from $1$ to $5$).
   - CUSUM Calibrated Limit $h$ (default $6.5$, adjustable from $2.0$ to $15.0$).
4. **Three Synchronized Canvas Visualizations:**
   - **Telemetry View:** Raw Canary Latency (orange), Control Latency (blue), and Workload Confounder (purple dashed).
   - **Contrast & Ground Truth:** Workload-adjusted contrast $\Delta z_t$ (teal) plotted directly against the ground-truth harmful regression $a_t$ (red dashed).
   - **Evidence & Decision Chart:** Recursive posterior harm probability $P(\text{Harm} \mid \mathbf{y}_{1:t})$ (green) plotted with calibrated hysteresis alarm/clear bands against normalized CUSUM (amber).
5. **Real-Time Decision State Banner:**
   - `PRE-ROLLOUT BASELINE STAGE` (Grey/Neutral)
   - `ROLLOUT HEALTHY — TELEMETRY IN SPEC` (Green)
   - `ALARM TRIGGERED: CANARY ROLLBACK MANDATED` (Red, pulsing with exact detection timestamp and delay)
   - `ROLLOUT RECOVERED: POST-ROLLBACK HEALTH RESTORED` (Blue)

---

### 2. How to Launch and Operate

#### Method A: Local HTTP Server (Recommended)
```bash
python demo/serve_demo.py --port 8080
```
- Automatically opens `http://localhost:8080/index.html` in your default browser.
- Press `Ctrl+C` in the terminal to stop the server when finished.

#### Method B: Direct File Open (Offline)
Because `demo/index.html` embeds the precomputed telemetry trajectories and relies exclusively on HTML5 Canvas (zero external CDN or remote JavaScript dependencies), it can be opened directly without a web server:
```bash
# Windows
start demo/index.html

# Linux
xdg-open demo/index.html
```

---

### 3. Recommended Walkthrough Sequence for Demonstrations

1. **Step 1: Select "Regression Recovery"**
   - Click `Play`. Observe pre-rollout stability ($t \le 180$).
   - At $t=180$, rollout starts. Canary latency gradually rises.
   - At $t=194$, posterior probability crosses $\tau_{\text{high}} = 0.85$, triggering `ALARM TRIGGERED: CANARY ROLLBACK MANDATED` (Detection delay: 14 min).
   - At $t=240$, the simulated automated rollback takes effect. Canary latency drops back to baseline.
   - At $t=248$, posterior drops below $\tau_{\text{low}} = 0.25$, triggering `ROLLOUT RECOVERED`.
2. **Step 2: Select "Class-Wide Correlated Shock"**
   - Demonstrates hierarchical grouping: only Class 0 canary instances degrade. The filter correctly tracks the class deviation state $\delta_{0,t}$ and detects harm within 12 minutes.
3. **Step 3: Select "Step Confounder + Canary Regression"**
   - A cluster-wide workload step (+0.33) shifts both canary and control streams.
   - Classical CUSUM is confounded by the step, accumulating false evidence.
   - Workload-adjusted contrast in the SSM strips out the step shift, detecting the true underlying software regression without false alarming.
4. **Step 4: Select "Isolated Transient Spike (Benign)"**
   - A sharp 5-minute latency spike hits 1 host.
   - Observe how CUSUM jumps abruptly toward alarm.
   - In contrast, the SSM posterior probability remains bounded and does not trigger an alarm, demonstrating state-space noise rejection.
