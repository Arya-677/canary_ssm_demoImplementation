# Demonstration Video Narration Script: Canary SSM V3
## 5-Minute Technical Audio Script

- **Target Audio Duration:** 5 minutes (~650 words spoken at a clear, deliberate pace of 130 words/min)
- **Speaker:** Primary Researcher / Technical Lead
- **Companion Storyboard:** `docs/research_release/DEMO_VIDEO_STORYBOARD.md`

---

### [0:00 - 0:35] Scene 1: Introduction & The Canary Confounding Dilemma

*(Visual: Title card, transition to live dashboard running at `localhost:8080`)*

> "Welcome to this demonstration of **Canary SSM V3**, an empirical investigation into hierarchical, inertia-constrained state-space models for safer software rollout decisions.
>
> In modern cloud infrastructure, rolling out new software builds to a canary fleet is our primary defense against widespread outages. But evaluating live canary telemetry is notoriously difficult. Metrics like latency are heavily confounded by cluster-wide traffic surges, background jobs, and network throttling.
>
> Classical detectors—like rolling-window tests in Netflix Kayenta or standard sequential CUSUM—frequently trigger premature rollbacks on benign noise or miss subtle, slow-creeping degradations. Today, we'll demonstrate how hierarchical state-space smoothing and finite-sample threshold calibration solve this dilemma."

---

### [0:35 - 1:15] Scene 2: Live Telemetry & Pre-Period Estimation

*(Visual: Dashboard running "Regression Recovery" preset. Click Play at 2x speed.)*

> "Here is our live interactive dashboard, operating completely self-contained and offline.
>
> On the top chart, we see raw telemetry from a 100-host fleet: the orange line represents our 10 canary hosts, the blue line represents 90 control hosts, and the dashed purple line tracks cluster workload.
>
> Notice the first 180 minutes: this is our pre-period baseline. In strict accordance with scientific causality safeguards, we fit all host baselines, workload sensitivities, and latent factor loadings exclusively on this pre-period window. No future data leaks into our models."

---

### [1:15 - 2:05] Scene 3: Harm Injection, State Tracking & Rollback Alarm

*(Visual: Time cursor crosses $t=180$. Middle canvas shows contrast; bottom shows posterior probability climbing. At $t=194$, red banner flashes.)*

> "At minute 180, the canary deployment begins. A 3.0% latency degradation is injected into the canary software.
>
> In the middle panel, our pre-period residualization isolates the contrast between canary and control, tracking the true ground-truth harm shown by the dashed red line.
>
> In the bottom panel, our recursive Kalman filter updates the marginal posterior probability that canary degradation exceeds the harm boundary.
>
> At minute 194—just 14 minutes after rollout—the posterior crosses our calibrated alarm threshold of 0.85. The status banner turns red: **ALARM TRIGGERED: CANARY ROLLBACK MANDATED**. Our automated policy halts the rollout, preventing a wider production failure."

---

### [2:05 - 2:45] Scene 4: Automated Recovery & Hysteresis Resumption

*(Visual: Time progresses past $t=240$. Canary latency returns to baseline. At $t=248$, banner turns blue.)*

> "Now observe what happens following rollback. At minute 240, the faulty software is remediated. Canary latency drops back to baseline.
>
> Rather than oscillating erratically, our model employs calibrated decision hysteresis. The posterior probability falls below our recovery threshold of 0.25 for five consecutive minutes.
>
> At minute 248, the banner transitions to blue: **ROLLOUT RECOVERED: POST-ROLLBACK HEALTH RESTORED**. The pipeline demonstrates fully autonomous, reversible lifecycle management."

---

### [2:45 - 3:35] Scene 5: Confounder Rejection vs Classical Baselines

*(Visual: Switch preset to "Step Confounder + Canary Regression". Run playback.)*

> "Let's examine why state-space modeling outperforms classical baselines under environmental stress. We'll switch to the 'Step Confounder' preset.
>
> Here, a massive cluster-wide traffic shift of +33% occurs at the exact moment of rollout. Look at the amber line in the bottom panel representing classical CUSUM: it is severely confounded by the step, accumulating false evidence.
>
> In contrast, our hierarchical filter dynamically decouples the shared environmental factor. The green posterior probability tracks only the true software regression, maintaining an exact, calibrated 5% false-alert budget."

---

### [3:35 - 4:15] Scene 6: Benign Transient Noise Rejection

*(Visual: Switch preset to "Isolated Transient Spike (Benign)". Hit Play.)*

> "Next, look at what happens during benign transient noise. In this scenario, a single host experiences an isolated 5-minute latency spike of +50%.
>
> In classical windowed systems, this single micro-burst triggers a premature rollback. But in our hierarchical model, state-space inertia and persistence scoring regularize the spike. The posterior stays safely below the alarm threshold, completely avoiding an unnecessary deployment halt."

---

### [4:15 - 5:00] Scene 7: Empirical Results, Trade-Offs & Conclusion

*(Visual: Display summary slides showing Figures 1, 2, and 4. Conclude with repository link.)*

> "Across 9,600 simulated rollouts and held-out test evaluations, the hierarchical state-space model reduced mean capped detection delay to **15.57 minutes**—a statistically significant 2.5-minute advantage over unpooled models and over 17 minutes faster than sequential GLR. Under heavy-tailed noise, it bound false alerts to 6.0%, whereas classical GLR exploded to 85.7%.
>
> But science demands transparency: our audit confirmed that hierarchical pooling introduces a **+9.46 minute penalty** when a defect is strictly isolated to a single host, because shrinkage pulls the local defect toward the fleet mean. In production, hierarchical models must be paired with extreme-value detectors.
>
> All code, fitted models, calibration manifests, and this interactive demo are fully archived and reproducible on GitHub. Thank you."
