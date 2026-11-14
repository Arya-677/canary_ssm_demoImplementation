# Demonstration Video Storyboard: Canary SSM V3
## 5-Minute Technical Video Walkthrough Plan

- **Target Duration:** 5 minutes (300 seconds)
- **Target Resolution:** 1920x1080 (1080p, 60fps)
- **Audio:** Narration with subtle background hum / clean audio
- **Screen Focus:** Split view between terminal / web dashboard at `http://localhost:8080`

---

### Scene-by-Scene Visual Breakdown

| Scene # | Time Window | Screen Visual & UI State | Key Interaction / Cursor Movement | Audio Narration Focus |
| :---: | :---: | :--- | :--- | :--- |
| **Scene 1** | `0:00 - 0:35` (35s) | Slide / Title Screen: "Hierarchical State-Space Models for Safer Canary Rollouts"<br>Transition to dashboard header | Pan across header badges: "V3 Research Prototype", "Gate G2 Validated", "Offline Engine" | Introduction: Motivation, cloud canary deployment challenges, uncalibrated false alarms in classical tooling. |
| **Scene 2** | `0:35 - 1:15` (40s) | Dashboard view: Preset "Regression Recovery"<br>Telemetry canvas showing Canary vs Control latency | Hit `Play`. Cursor follows vertical blue cursor moving across pre-period into rollout window ($t=180$). | Explaining raw telemetry, diurnal workload confounder, and the pre-period nuisance baseline. |
| **Scene 3** | `1:15 - 2:05` (50s) | Contrast canvas & Posterior Probability canvas<br>Red dashed line represents ground truth $a_t$ | Watch posterior probability curve climb. State banner turns flashing red at $t=194$: `ALARM TRIGGERED`. | Decomposing the signal: How Kalman state estimation separates true harm from noise. The role of calibrated threshold $\tau_{\text{high}} = 0.85$. |
| **Scene 4** | `2:05 - 2:45` (40s) | Post-rollback window ($t > 240$)<br>Canary latency drops back to baseline | At $t=248$, state banner turns blue: `ROLLOUT RECOVERED`. Adjust $\tau_{\text{low}}$ slider to show sensitivity. | Demonstrating automated hysteresis recovery: Clearing the alarm without operator intervention when latency normalizes. |
| **Scene 5** | `2:45 - 3:35` (50s) | Switch preset to "Step Confounder + Canary Regression"<br>Workload step jump at $t=180$ | Show CUSUM score drifting upward erratically. Show adjusted contrast remaining stable and tracking true harm. | The confounding problem: Why classical CUSUM/EWMA fail under shared steps, and how factor residualization decouples the shock. |
| **Scene 6** | `3:35 - 4:15` (40s) | Switch preset to "Isolated Transient Spike (Benign)"<br>Sharp 5-minute spike on 1 canary host | Zoom in on probability chart: SSM stays below threshold, avoiding premature rollback. | Noise rejection: How latent state smoothing prevents costly false pauses on benign micro-bursts. |
| **Scene 7** | `4:15 - 5:00` (45s) | Slide view: Summary of Experimental Results (Figures 1, 2, 4)<br>Limitations & GitHub link | Highlight: 15.57m delay, 17m advantage over GLR, single-host cost check (+9.5m), open-source repo. | Synthesis: Empirical findings, the localized shrinkage trade-off, scientific non-claims, and handoff. |
