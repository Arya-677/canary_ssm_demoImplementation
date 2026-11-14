"""Script to generate demo/index.html with embedded data."""
import json
from pathlib import Path

data_path = Path("demo/data.json")
with open(data_path, "r", encoding="utf-8") as f:
    demo_data_json = f.read()

html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Canary SSM V3 — Interactive Research & Decision Demo</title>
  <style>
    :root {{
      --bg-primary: #0f172a;
      --bg-secondary: #1e293b;
      --bg-card: #1e293b;
      --border-color: #334155;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --accent-blue: #38bdf8;
      --accent-green: #22c55e;
      --accent-amber: #f59e0b;
      --accent-rose: #f43f5e;
      --accent-purple: #c084fc;
      --accent-orange: #fb923c;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg-primary);
      color: var(--text-main);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      line-height: 1.5;
      padding: 16px;
    }}
    .container {{
      max-width: 1400px;
      margin: 0 auto;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }}
    header {{
      background: var(--bg-secondary);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 16px 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
    }}
    .header-titles h1 {{
      font-size: 1.4rem;
      font-weight: 700;
      color: var(--text-main);
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .header-titles p {{
      font-size: 0.85rem;
      color: var(--text-muted);
      margin-top: 2px;
    }}
    .badge {{
      display: inline-block;
      font-size: 0.72rem;
      padding: 2px 8px;
      border-radius: 4px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .badge-v3 {{ background: #0284c7; color: #fff; }}
    .badge-gate {{ background: #15803d; color: #fff; }}
    .badge-offline {{ background: #475569; color: #e2e8f0; }}

    /* Layout grid */
    .dashboard-grid {{
      display: grid;
      grid-template-columns: 340px 1fr;
      gap: 16px;
    }}
    @media (max-width: 1024px) {{
      .dashboard-grid {{
        grid-template-columns: 1fr;
      }}
    }}

    .card {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 16px;
    }}
    .card-title {{
      font-size: 0.95rem;
      font-weight: 600;
      color: var(--text-main);
      margin-bottom: 12px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 8px;
    }}

    /* Controls Panel */
    .controls-panel {{
      display: flex;
      flex-direction: column;
      gap: 16px;
    }}
    .form-group {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    label {{
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    select, input[type="range"] {{
      width: 100%;
      background: #0f172a;
      border: 1px solid var(--border-color);
      color: var(--text-main);
      border-radius: 6px;
      padding: 8px;
      font-size: 0.9rem;
    }}
    .slider-row {{
      display: flex;
      justify-content: space-between;
      font-size: 0.8rem;
      color: var(--text-muted);
    }}
    .btn-row {{
      display: flex;
      gap: 8px;
    }}
    button {{
      flex: 1;
      padding: 8px 12px;
      font-size: 0.85rem;
      font-weight: 600;
      border: 1px solid var(--border-color);
      border-radius: 6px;
      background: #334155;
      color: #fff;
      cursor: pointer;
      transition: all 0.15s ease;
    }}
    button:hover {{
      background: #475569;
    }}
    button.primary {{
      background: #0284c7;
      border-color: #0369a1;
    }}
    button.primary:hover {{
      background: #0369a1;
    }}

    /* Status Banner */
    .status-banner {{
      padding: 12px 16px;
      border-radius: 6px;
      font-weight: 700;
      font-size: 0.95rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
      border: 1px solid transparent;
    }}
    .status-healthy {{
      background: rgba(34, 197, 94, 0.15);
      border-color: var(--accent-green);
      color: #86efac;
    }}
    .status-alarm {{
      background: rgba(244, 63, 94, 0.2);
      border-color: var(--accent-rose);
      color: #fda4af;
      animation: pulse 1.5s infinite;
    }}
    .status-recovered {{
      background: rgba(56, 189, 248, 0.15);
      border-color: var(--accent-blue);
      color: #bae6fd;
    }}
    @keyframes pulse {{
      0%, 100% {{ opacity: 1; }}
      50% {{ opacity: 0.7; }}
    }}

    /* Charts Container */
    .charts-container {{
      display: flex;
      flex-direction: column;
      gap: 16px;
    }}
    .chart-wrapper {{
      position: relative;
      height: 180px;
      background: #0b1120;
      border: 1px solid var(--border-color);
      border-radius: 6px;
      overflow: hidden;
    }}
    canvas {{
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
    }}
    .chart-legend {{
      position: absolute;
      top: 8px;
      left: 12px;
      display: flex;
      gap: 12px;
      font-size: 0.75rem;
      background: rgba(15, 23, 42, 0.75);
      padding: 3px 8px;
      border-radius: 4px;
      border: 1px solid rgba(51, 65, 85, 0.5);
      pointer-events: none;
    }}
    .legend-item {{
      display: flex;
      align-items: center;
      gap: 5px;
    }}
    .legend-color {{
      width: 10px;
      height: 10px;
      border-radius: 2px;
    }}

    /* Metrics Grid */
    .metrics-summary {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 10px;
      margin-bottom: 16px;
    }}
    @media (max-width: 640px) {{
      .metrics-summary {{ grid-template-columns: repeat(2, 1fr); }}
    }}
    .metric-box {{
      background: #0f172a;
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 10px;
    }}
    .metric-label {{
      font-size: 0.7rem;
      color: var(--text-muted);
      text-transform: uppercase;
      font-weight: 600;
    }}
    .metric-value {{
      font-size: 1.1rem;
      font-weight: 700;
      color: var(--text-main);
      margin-top: 2px;
    }}

    /* Scientific Notes */
    .notes-box {{
      font-size: 0.82rem;
      color: var(--text-muted);
      background: #0f172a;
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 12px;
      line-height: 1.6;
    }}
    .notes-box strong {{
      color: var(--text-main);
    }}
    .notes-box ul {{
      margin-left: 18px;
      margin-top: 6px;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="header-titles">
        <h1>
          <span>Canary SSM V3 Decision Prototype</span>
          <span class="badge badge-v3">V3 Research</span>
          <span class="badge badge-gate">Gate G2 Validated</span>
          <span class="badge badge-offline">Offline Engine</span>
        </h1>
        <p>Hierarchical State-Space Smoothing vs Classical Baselines under Inertia and Rollout Perturbations</p>
      </div>
      <div>
        <a href="https://github.com" style="color: var(--accent-blue); font-size: 0.8rem; text-decoration: none;">Canary SSM Docs</a>
      </div>
    </header>

    <div class="dashboard-grid">
      <!-- Left Controls Column -->
      <div class="controls-panel">
        <div class="card">
          <div class="card-title">Scenario Preset</div>
          <div class="form-group">
            <select id="scenarioSelect">
              <option value="regression_recovery">Regression Recovery (Rollback)</option>
              <option value="class_wide">Class-Wide Correlated Shock</option>
              <option value="broad_fleet">Broad Fleet Shared Anomaly</option>
              <option value="single_host_persistent">Single-Host Persistent Defect</option>
              <option value="step_plus_harm">Step Confounder + Canary Regression</option>
              <option value="iso_spike_1host">Isolated Transient Spike (Benign)</option>
            </select>
            <p id="scenarioDesc" style="font-size: 0.8rem; color: var(--text-muted); margin-top: 6px;"></p>
          </div>
        </div>

        <div class="card">
          <div class="card-title">Playback Controller</div>
          <div class="form-group">
            <div class="btn-row">
              <button id="playBtn" class="primary">Play</button>
              <button id="stepBtn">Step +1</button>
              <button id="resetBtn">Reset</button>
            </div>
            <div style="margin-top: 8px;">
              <div class="slider-row">
                <span>Current Step: <strong id="stepVal" style="color: var(--accent-blue)">0</strong> / 119</span>
                <span>Time: <strong id="timeVal">140</strong> min</span>
              </div>
              <input type="range" id="timeSlider" min="0" max="119" value="0">
            </div>
            <div style="margin-top: 6px; display: flex; justify-content: space-between; align-items: center;">
              <span style="font-size: 0.8rem; color: var(--text-muted)">Playback Speed:</span>
              <select id="speedSelect" style="width: 100px; padding: 4px 8px; font-size: 0.8rem;">
                <option value="150">1x (Slow)</option>
                <option value="75" selected>2x (Normal)</option>
                <option value="30">5x (Fast)</option>
              </select>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-title">Decision Thresholds</div>
          <div class="form-group">
            <div class="slider-row">
              <span>SSM Alarm Threshold (&tau;<sub>high</sub>)</span>
              <span id="tauHighVal" style="color: var(--accent-rose); font-weight: bold;">0.85</span>
            </div>
            <input type="range" id="tauHighSlider" min="0.50" max="0.99" step="0.01" value="0.85">

            <div class="slider-row" style="margin-top: 10px;">
              <span>SSM Recovery Threshold (&tau;<sub>low</sub>)</span>
              <span id="tauLowVal" style="color: var(--accent-blue); font-weight: bold;">0.25</span>
            </div>
            <input type="range" id="tauLowSlider" min="0.05" max="0.50" step="0.01" value="0.25">

            <div class="slider-row" style="margin-top: 10px;">
              <span>Min Consecutive Crossings (k)</span>
              <span id="kVal" style="color: var(--accent-amber); font-weight: bold;">2</span>
            </div>
            <input type="range" id="kSlider" min="1" max="5" step="1" value="2">

            <div class="slider-row" style="margin-top: 10px;">
              <span>CUSUM Calibrated Limit (h)</span>
              <span id="cusumHVal" style="color: var(--accent-amber); font-weight: bold;">6.50</span>
            </div>
            <input type="range" id="cusumHSlider" min="2.0" max="15.0" step="0.5" value="6.5">
          </div>
        </div>

        <div class="card">
          <div class="card-title">Scientific Caveats</div>
          <div class="notes-box">
            <strong>Preregistered Constraints:</strong>
            <ul>
              <li>Univariate latency response only; multivariate extensions require covariance calibration.</li>
              <li>Calibrated at Gate G2 false-alert budget (Beta-Binomial p &ge; 0.01).</li>
              <li>H2 (two-scale inertia) and H3 (hysteresis false alarm reduction) did not achieve statistical significance; report reflects empirical findings.</li>
              <li>Synthetic benchmark prototype; not approved for production automation without live shadow-mode validation.</li>
            </ul>
          </div>
        </div>
      </div>

      <!-- Right Main Visualization Area -->
      <div>
        <div id="statusBanner" class="status-banner status-healthy">
          <span id="statusText">STATUS: ROLLOUT HEALTHY — TELEMETRY IN SPEC</span>
          <span id="decisionLatencyBadge" style="font-size: 0.8rem; font-weight: normal; opacity: 0.9;">No Alarms</span>
        </div>

        <div class="metrics-summary">
          <div class="metric-box">
            <div class="metric-label">Canary Latency</div>
            <div class="metric-value" id="mCanary">-- ms</div>
          </div>
          <div class="metric-box">
            <div class="metric-label">Control Latency</div>
            <div class="metric-value" id="mControl">-- ms</div>
          </div>
          <div class="metric-box">
            <div class="metric-label">SSM P(Harm)</div>
            <div class="metric-value" id="mSSM">0.0%</div>
          </div>
          <div class="metric-box">
            <div class="metric-label">CUSUM Score</div>
            <div class="metric-value" id="mCusum">0.00</div>
          </div>
        </div>

        <div class="charts-container">
          <!-- Chart 1: Latency & Workload -->
          <div class="card" style="padding: 10px;">
            <div style="font-size: 0.8rem; font-weight: 600; margin-bottom: 6px; color: var(--text-muted); display: flex; justify-content: space-between;">
              <span>RAW TELEMETRY: CANARY VS CONTROL LATENCY</span>
              <span>Workload Confounder (Normalized)</span>
            </div>
            <div class="chart-wrapper">
              <canvas id="canvasTelemetry"></canvas>
              <div class="chart-legend">
                <div class="legend-item"><div class="legend-color" style="background: var(--accent-orange);"></div>Canary</div>
                <div class="legend-item"><div class="legend-color" style="background: var(--accent-blue);"></div>Control</div>
                <div class="legend-item"><div class="legend-color" style="background: var(--accent-purple);"></div>Workload (w)</div>
              </div>
            </div>
          </div>

          <!-- Chart 2: Contrast & True Harm Effect -->
          <div class="card" style="padding: 10px;">
            <div style="font-size: 0.8rem; font-weight: 600; margin-bottom: 6px; color: var(--text-muted); display: flex; justify-content: space-between;">
              <span>WORKLOAD-ADJUSTED CONTRAST & GROUND TRUTH HARMFUL SHOCK</span>
              <span>Rollout Starts at t=180</span>
            </div>
            <div class="chart-wrapper">
              <canvas id="canvasContrast"></canvas>
              <div class="chart-legend">
                <div class="legend-item"><div class="legend-color" style="background: #2dd4bf;"></div>Adjusted Contrast</div>
                <div class="legend-item"><div class="legend-color" style="background: var(--accent-rose);"></div>True Harm Effect (a)</div>
              </div>
            </div>
          </div>

          <!-- Chart 3: SSM Posterior vs CUSUM -->
          <div class="card" style="padding: 10px;">
            <div style="font-size: 0.8rem; font-weight: 600; margin-bottom: 6px; color: var(--text-muted); display: flex; justify-content: space-between;">
              <span>DECISION EVIDENCE: HIERARCHICAL SSM POSTERIOR VS CUSUM</span>
              <span>Hysteresis Bands [&tau;<sub>low</sub>, &tau;<sub>high</sub>]</span>
            </div>
            <div class="chart-wrapper">
              <canvas id="canvasDecision"></canvas>
              <div class="chart-legend">
                <div class="legend-item"><div class="legend-color" style="background: var(--accent-green);"></div>SSM P(Harm | y)</div>
                <div class="legend-item"><div class="legend-color" style="background: var(--accent-amber);"></div>CUSUM Normalized</div>
                <div class="legend-item"><div class="legend-color" style="background: rgba(244, 63, 94, 0.5);"></div>Alarm Zone</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    // Embedded study dataset
    const DATA = {demo_data_json};

    // State
    let currentScenarioKey = "regression_recovery";
    let curIdx = 0;
    let isPlaying = false;
    let playTimer = null;
    let tauHigh = 0.85;
    let tauLow = 0.25;
    let kReq = 2;
    let cusumH = 6.5;

    // DOM Elements
    const scenarioSelect = document.getElementById("scenarioSelect");
    const scenarioDesc = document.getElementById("scenarioDesc");
    const playBtn = document.getElementById("playBtn");
    const stepBtn = document.getElementById("stepBtn");
    const resetBtn = document.getElementById("resetBtn");
    const timeSlider = document.getElementById("timeSlider");
    const stepVal = document.getElementById("stepVal");
    const timeVal = document.getElementById("timeVal");
    const speedSelect = document.getElementById("speedSelect");

    const tauHighSlider = document.getElementById("tauHighSlider");
    const tauHighVal = document.getElementById("tauHighVal");
    const tauLowSlider = document.getElementById("tauLowSlider");
    const tauLowVal = document.getElementById("tauLowVal");
    const kSlider = document.getElementById("kSlider");
    const kVal = document.getElementById("kVal");
    const cusumHSlider = document.getElementById("cusumHSlider");
    const cusumHVal = document.getElementById("cusumHVal");

    const statusBanner = document.getElementById("statusBanner");
    const statusText = document.getElementById("statusText");
    const decisionLatencyBadge = document.getElementById("decisionLatencyBadge");

    const mCanary = document.getElementById("mCanary");
    const mControl = document.getElementById("mControl");
    const mSSM = document.getElementById("mSSM");
    const mCusum = document.getElementById("mCusum");

    const cvTelemetry = document.getElementById("canvasTelemetry");
    const cvContrast = document.getElementById("canvasContrast");
    const cvDecision = document.getElementById("canvasDecision");

    function resizeCanvas(cv) {{
      const rect = cv.parentElement.getBoundingClientRect();
      cv.width = rect.width * window.devicePixelRatio;
      cv.height = rect.height * window.devicePixelRatio;
    }}

    function resizeAll() {{
      resizeCanvas(cvTelemetry);
      resizeCanvas(cvContrast);
      resizeCanvas(cvDecision);
      render();
    }}
    window.addEventListener("resize", resizeAll);

    function initScenario() {{
      const sc = DATA[currentScenarioKey];
      scenarioDesc.textContent = sc.desc;
      curIdx = 0;
      timeSlider.value = 0;
      render();
    }}

    function computeDecisionState(idx) {{
      const sc = DATA[currentScenarioKey];
      let alarmAt = -1;
      let recoverAt = -1;
      let consecutiveHigh = 0;
      let consecutiveLow = 0;
      let inAlarm = false;

      for (let i = 0; i <= idx; i++) {{
        const p = sc.ssm_prob[i];
        if (!inAlarm) {{
          if (p >= tauHigh) {{
            consecutiveHigh++;
            if (consecutiveHigh >= kReq) {{
              inAlarm = true;
              alarmAt = sc.t[i];
            }}
          }} else {{
            consecutiveHigh = 0;
          }}
        }} else {{
          if (p <= tauLow) {{
            consecutiveLow++;
            if (consecutiveLow >= kReq) {{
              inAlarm = false;
              recoverAt = sc.t[i];
            }}
          }} else {{
            consecutiveLow = 0;
          }}
        }}
      }}
      return {{ inAlarm, alarmAt, recoverAt }};
    }}

    function render() {{
      const sc = DATA[currentScenarioKey];
      if (!sc) return;

      const n = sc.t.length;
      stepVal.textContent = curIdx;
      timeVal.textContent = sc.t[curIdx];
      timeSlider.value = curIdx;

      mCanary.textContent = sc.canary_latency[curIdx].toFixed(2) + " ms";
      mControl.textContent = sc.control_latency[curIdx].toFixed(2) + " ms";
      mSSM.textContent = (sc.ssm_prob[curIdx] * 100).toFixed(1) + "%";
      mCusum.textContent = sc.cusum_score[curIdx].toFixed(2);

      const dec = computeDecisionState(curIdx);
      if (dec.inAlarm) {{
        statusBanner.className = "status-banner status-alarm";
        statusText.textContent = "ALARM TRIGGERED: CANARY ROLLBACK MANDATED";
        decisionLatencyBadge.textContent = "Halted at t=" + dec.alarmAt + " min (Delay: " + (dec.alarmAt - sc.rollout_time) + " min)";
      }} else if (dec.recoverAt > 0 && curIdx >= (sc.t.indexOf(dec.recoverAt))) {{
        statusBanner.className = "status-banner status-recovered";
        statusText.textContent = "ROLLOUT RECOVERED: POST-ROLLBACK HEALTH RESTORED";
        decisionLatencyBadge.textContent = "Cleared at t=" + dec.recoverAt + " min";
      }} else {{
        statusBanner.className = "status-banner status-healthy";
        statusText.textContent = curIdx < (sc.t.indexOf(sc.rollout_time)) ? "PRE-ROLLOUT BASELINE STAGE" : "ROLLOUT HEALTHY — TELEMETRY IN SPEC";
        decisionLatencyBadge.textContent = "Telemetry nominal";
      }}

      drawChart(cvTelemetry, [
        {{ data: sc.canary_latency, color: "#fb923c", width: 2 }},
        {{ data: sc.control_latency, color: "#38bdf8", width: 1.5 }},
        {{ data: sc.workload.map(w => 20 + w * 4), color: "#c084fc", width: 1, dash: [4, 4] }}
      ], sc.rollout_time, sc.t);

      drawChart(cvContrast, [
        {{ data: sc.contrast, color: "#2dd4bf", width: 1.5 }},
        {{ data: sc.true_effect, color: "#f43f5e", width: 2, dash: [4, 2] }}
      ], sc.rollout_time, sc.t, true);

      drawDecisionChart(cvDecision, sc.ssm_prob, sc.cusum_score, sc.rollout_time, sc.t);
    }}

    function drawChart(cv, seriesList, rolloutTime, tAxis, zeroLine=false) {{
      const ctx = cv.getContext("2d");
      const dpr = window.devicePixelRatio || 1;
      const w = cv.width / dpr;
      const h = cv.height / dpr;
      ctx.save();
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, w, h);

      const padL = 40, padR = 20, padT = 15, padB = 25;
      const plotW = w - padL - padR;
      const plotH = h - padT - padB;

      // Find min / max across series
      let yMin = Infinity, yMax = -Infinity;
      seriesList.forEach(s => {{
        s.data.forEach(v => {{
          if (v < yMin) yMin = v;
          if (v > yMax) yMax = v;
        }});
      }});
      if (zeroLine) {{
        yMin = Math.min(yMin, -2);
        yMax = Math.max(yMax, 2);
      }}
      const yRange = (yMax - yMin) || 1;
      yMin -= yRange * 0.05;
      yMax += yRange * 0.05;

      function getX(i) {{ return padL + (i / (seriesList[0].data.length - 1)) * plotW; }}
      function getY(v) {{ return padT + (1 - (v - yMin) / (yMax - yMin)) * plotH; }}

      // Grid lines
      ctx.strokeStyle = "#1e293b";
      ctx.lineWidth = 1;
      for (let i = 0; i <= 4; i++) {{
        const yVal = yMin + (i / 4) * (yMax - yMin);
        const y = getY(yVal);
        ctx.beginPath();
        ctx.moveTo(padL, y);
        ctx.lineTo(padL + plotW, y);
        ctx.stroke();

        ctx.fillStyle = "#64748b";
        ctx.font = "10px monospace";
        ctx.textAlign = "right";
        ctx.fillText(yVal.toFixed(1), padL - 6, y + 3);
      }}

      // Rollout vertical dashed line
      const rIdx = tAxis.indexOf(rolloutTime);
      if (rIdx >= 0) {{
        const rx = getX(rIdx);
        ctx.save();
        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = "#94a3b8";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(rx, padT);
        ctx.lineTo(rx, padT + plotH);
        ctx.stroke();
        ctx.fillStyle = "#94a3b8";
        ctx.font = "9px sans-serif";
        ctx.textAlign = "left";
        ctx.fillText("Rollout", rx + 4, padT + 10);
        ctx.restore();
      }}

      // Series lines up to curIdx
      seriesList.forEach(s => {{
        ctx.save();
        ctx.strokeStyle = s.color;
        ctx.lineWidth = s.width;
        if (s.dash) ctx.setLineDash(s.dash);

        // History
        ctx.beginPath();
        for (let i = 0; i <= curIdx; i++) {{
          const x = getX(i);
          const y = getY(s.data[i]);
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }}
        ctx.stroke();

        // Future faint line
        ctx.beginPath();
        ctx.globalAlpha = 0.2;
        ctx.setLineDash([2, 2]);
        for (let i = curIdx; i < s.data.length; i++) {{
          const x = getX(i);
          const y = getY(s.data[i]);
          if (i === curIdx) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }}
        ctx.stroke();
        ctx.restore();
      }});

      // Vertical cursor at curIdx
      const curX = getX(curIdx);
      ctx.strokeStyle = "#38bdf8";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(curX, padT);
      ctx.lineTo(curX, padT + plotH);
      ctx.stroke();

      ctx.restore();
    }}

    function drawDecisionChart(cv, ssmProb, cusum, rolloutTime, tAxis) {{
      const ctx = cv.getContext("2d");
      const dpr = window.devicePixelRatio || 1;
      const w = cv.width / dpr;
      const h = cv.height / dpr;
      ctx.save();
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, w, h);

      const padL = 40, padR = 20, padT = 15, padB = 25;
      const plotW = w - padL - padR;
      const plotH = h - padT - padB;

      function getX(i) {{ return padL + (i / (ssmProb.length - 1)) * plotW; }}
      function getYProb(p) {{ return padT + (1 - p) * plotH; }}

      // Hysteresis Band: tauHigh to 1.0 (Alarm zone)
      const yHigh = getYProb(tauHigh);
      ctx.fillStyle = "rgba(244, 63, 94, 0.12)";
      ctx.fillRect(padL, padT, plotW, yHigh - padT);

      // tauLow to 0 (Clear zone)
      const yLow = getYProb(tauLow);
      ctx.fillStyle = "rgba(56, 189, 248, 0.08)";
      ctx.fillRect(padL, yLow, plotW, padT + plotH - yLow);

      // Threshold lines
      ctx.strokeStyle = "rgba(244, 63, 94, 0.7)";
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(padL, yHigh);
      ctx.lineTo(padL + plotW, yHigh);
      ctx.stroke();

      ctx.strokeStyle = "rgba(56, 189, 248, 0.7)";
      ctx.beginPath();
      ctx.moveTo(padL, yLow);
      ctx.lineTo(padL + plotW, yLow);
      ctx.stroke();
      ctx.setLineDash([]);

      // Probability axis labels
      [0.0, 0.25, 0.5, 0.75, 1.0].forEach(p => {{
        const y = getYProb(p);
        ctx.fillStyle = "#64748b";
        ctx.font = "10px monospace";
        ctx.textAlign = "right";
        ctx.fillText((p * 100).toFixed(0) + "%", padL - 6, y + 3);
      }});

      // Draw SSM Prob line
      ctx.strokeStyle = "#22c55e";
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      for (let i = 0; i <= curIdx; i++) {{
        const x = getX(i);
        const y = getYProb(ssmProb[i]);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }}
      ctx.stroke();

      // Future faint line
      ctx.beginPath();
      ctx.strokeStyle = "#22c55e";
      ctx.globalAlpha = 0.25;
      ctx.setLineDash([2, 2]);
      for (let i = curIdx; i < ssmProb.length; i++) {{
        const x = getX(i);
        const y = getYProb(ssmProb[i]);
        if (i === curIdx) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }}
      ctx.stroke();
      ctx.globalAlpha = 1.0;
      ctx.setLineDash([]);

      // Draw CUSUM scaled
      const maxC = 15.0;
      ctx.strokeStyle = "#f59e0b";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      for (let i = 0; i <= curIdx; i++) {{
        const cNorm = Math.min(1.0, cusum[i] / maxC);
        const x = getX(i);
        const y = getYProb(cNorm);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }}
      ctx.stroke();

      // Cursor
      const curX = getX(curIdx);
      ctx.strokeStyle = "#38bdf8";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(curX, padT);
      ctx.lineTo(curX, padT + plotH);
      ctx.stroke();

      ctx.restore();
    }}

    // Event listeners
    scenarioSelect.addEventListener("change", (e) => {{
      currentScenarioKey = e.target.value;
      initScenario();
    }});

    timeSlider.addEventListener("input", (e) => {{
      curIdx = parseInt(e.target.value);
      render();
    }});

    playBtn.addEventListener("click", () => {{
      if (isPlaying) {{
        clearInterval(playTimer);
        isPlaying = false;
        playBtn.textContent = "Play";
        playBtn.className = "primary";
      }} else {{
        isPlaying = true;
        playBtn.textContent = "Pause";
        playBtn.className = "";
        const spd = parseInt(speedSelect.value);
        playTimer = setInterval(() => {{
          if (curIdx < 119) {{
            curIdx++;
            render();
          }} else {{
            clearInterval(playTimer);
            isPlaying = false;
            playBtn.textContent = "Play";
            playBtn.className = "primary";
          }}
        }}, spd);
      }}
    }});

    stepBtn.addEventListener("click", () => {{
      if (curIdx < 119) {{
        curIdx++;
        render();
      }}
    }});

    resetBtn.addEventListener("click", () => {{
      if (isPlaying) {{
        clearInterval(playTimer);
        isPlaying = false;
        playBtn.textContent = "Play";
        playBtn.className = "primary";
      }}
      curIdx = 0;
      render();
    }});

    tauHighSlider.addEventListener("input", (e) => {{
      tauHigh = parseFloat(e.target.value);
      tauHighVal.textContent = tauHigh.toFixed(2);
      render();
    }});
    tauLowSlider.addEventListener("input", (e) => {{
      tauLow = parseFloat(e.target.value);
      tauLowVal.textContent = tauLow.toFixed(2);
      render();
    }});
    kSlider.addEventListener("input", (e) => {{
      kReq = parseInt(e.target.value);
      kVal.textContent = kReq;
      render();
    }});
    cusumHSlider.addEventListener("input", (e) => {{
      cusumH = parseFloat(e.target.value);
      cusumHVal.textContent = cusumH.toFixed(1);
      render();
    }});

    // Init on load
    window.addEventListener("DOMContentLoaded", () => {{
      resizeAll();
      initScenario();
    }});
  </script>
</body>
</html>
'''

with open("demo/index.html", "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"demo/index.html created successfully ({len(html_content)} bytes).")
