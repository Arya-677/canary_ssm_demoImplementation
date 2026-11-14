# Formal Evaluation Report: Preregistered Inertia & Hysteresis Study (V3)

_Generated strictly from saved CSV outputs in `results/study_inertia/` according to the decision rules in `docs/PREREGISTRATION_V3.md`._

---

## 1. Calibration Validity Audit (Gate G2)

Thresholds calibrated on $B = 2,000$ exchangeable null rollouts (`study_inertia_cal`) and evaluated on $n_{\text{val}} = 2,000$ independent validation nulls (`study_inertia_val`). The target false alarm rate is $\alpha = 0.05$. Under the Beta-Binomial exact validity test, all cells require $p_{\text{bb}} > 0.001$ to be evaluable.

| Regime | Method | $m_{\text{on}}$ | $B$ | $k_{\text{order}}$ | $h_{\text{on}}$ | $h_{\text{off}}$ | Alerts | $n_{\text{val}}$ | FAR | 95% CI Lower | 95% CI Upper | $p_{\text{bb}}$ (two-sided) | Gate G2 Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| plain | indep_ssm | 1 | 2000 | 1901 | -1.0155 | -2.9280 | 86 | 2000 | 0.0430 | 0.0345 | 0.0528 | 0.3290 | PASS |
| plain | indep_ssm | 3 | 2000 | 1901 | -1.1655 | -3.0030 | 91 | 2000 | 0.0455 | 0.0368 | 0.0556 | 0.5532 | PASS |
| plain | indep_ssm | 5 | 2000 | 1901 | -1.2738 | -3.0571 | 89 | 2000 | 0.0445 | 0.0359 | 0.0545 | 0.4562 | PASS |
| plain | indep_ssm | 10 | 2000 | 1901 | -1.4831 | -3.1618 | 100 | 2000 | 0.0500 | 0.0409 | 0.0605 | 1.0000 | PASS |
| plain | indep_ssm | 15 | 2000 | 1901 | -1.6749 | -3.2577 | 87 | 2000 | 0.0435 | 0.0350 | 0.0534 | 0.3688 | PASS |
| plain | hier_ssm | 1 | 2000 | 1901 | -2.8013 | -5.3772 | 83 | 2000 | 0.0415 | 0.0332 | 0.0512 | 0.2259 | PASS |
| plain | hier_ssm | 3 | 2000 | 1901 | -3.0413 | -5.4972 | 80 | 2000 | 0.0400 | 0.0318 | 0.0495 | 0.1471 | PASS |
| plain | hier_ssm | 5 | 2000 | 1901 | -3.1925 | -5.5728 | 78 | 2000 | 0.0390 | 0.0309 | 0.0484 | 0.1071 | PASS |
| plain | hier_ssm | 10 | 2000 | 1901 | -3.5132 | -5.7331 | 78 | 2000 | 0.0390 | 0.0309 | 0.0484 | 0.1071 | PASS |
| plain | hier_ssm | 15 | 2000 | 1901 | -3.8080 | -5.8805 | 88 | 2000 | 0.0440 | 0.0354 | 0.0539 | 0.4113 | PASS |
| plain | hier_ts | 1 | 2000 | 1901 | -2.8013 | -5.3772 | 83 | 2000 | 0.0415 | 0.0332 | 0.0512 | 0.2259 | PASS |
| plain | hier_ts | 3 | 2000 | 1901 | -3.0413 | -5.4972 | 80 | 2000 | 0.0400 | 0.0318 | 0.0495 | 0.1471 | PASS |
| plain | hier_ts | 5 | 2000 | 1901 | -3.1925 | -5.5728 | 78 | 2000 | 0.0390 | 0.0309 | 0.0484 | 0.1071 | PASS |
| plain | hier_ts | 10 | 2000 | 1901 | -3.5132 | -5.7331 | 78 | 2000 | 0.0390 | 0.0309 | 0.0484 | 0.1071 | PASS |
| plain | hier_ts | 15 | 2000 | 1901 | -3.8080 | -5.8805 | 88 | 2000 | 0.0440 | 0.0354 | 0.0539 | 0.4113 | PASS |
| plain | adj_cusum | 1 | 2000 | 1901 | 30.0282 | 17.5777 | 84 | 2000 | 0.0420 | 0.0336 | 0.0517 | 0.2575 | PASS |
| plain | adj_cusum | 3 | 2000 | 1901 | 29.0012 | 17.0643 | 87 | 2000 | 0.0435 | 0.0350 | 0.0534 | 0.3688 | PASS |
| plain | adj_cusum | 5 | 2000 | 1901 | 27.8191 | 16.4732 | 85 | 2000 | 0.0425 | 0.0341 | 0.0523 | 0.2919 | PASS |
| plain | adj_cusum | 10 | 2000 | 1901 | 25.4544 | 15.2909 | 80 | 2000 | 0.0400 | 0.0318 | 0.0495 | 0.1471 | PASS |
| plain | adj_cusum | 15 | 2000 | 1901 | 23.3975 | 14.2624 | 85 | 2000 | 0.0425 | 0.0341 | 0.0523 | 0.2919 | PASS |
| plain | glr_window | 1 | 2000 | 1901 | 22.1013 | 14.7486 | 93 | 2000 | 0.0465 | 0.0377 | 0.0567 | 0.6581 | PASS |
| plain | glr_window | 3 | 2000 | 1901 | 19.8380 | 13.6169 | 88 | 2000 | 0.0440 | 0.0354 | 0.0539 | 0.4113 | PASS |
| plain | glr_window | 5 | 2000 | 1901 | 18.7067 | 13.0512 | 81 | 2000 | 0.0405 | 0.0323 | 0.0501 | 0.1708 | PASS |
| plain | glr_window | 10 | 2000 | 1901 | 16.8806 | 12.1382 | 82 | 2000 | 0.0410 | 0.0327 | 0.0506 | 0.1970 | PASS |
| plain | glr_window | 15 | 2000 | 1901 | 15.2480 | 11.3219 | 94 | 2000 | 0.0470 | 0.0381 | 0.0572 | 0.7130 | PASS |
| step | indep_ssm | 1 | 2000 | 1901 | -0.0118 | -1.0250 | 100 | 2000 | 0.0500 | 0.0409 | 0.0605 | 1.0000 | PASS |
| step | indep_ssm | 3 | 2000 | 1901 | -0.0150 | -1.0266 | 101 | 2000 | 0.0505 | 0.0413 | 0.0610 | 0.9422 | PASS |
| step | indep_ssm | 5 | 2000 | 1901 | -0.0194 | -1.0288 | 102 | 2000 | 0.0510 | 0.0418 | 0.0616 | 0.8849 | PASS |
| step | indep_ssm | 10 | 2000 | 1901 | -0.0225 | -1.0304 | 97 | 2000 | 0.0485 | 0.0395 | 0.0588 | 0.8839 | PASS |
| step | indep_ssm | 15 | 2000 | 1901 | -0.0313 | -1.0348 | 98 | 2000 | 0.0490 | 0.0400 | 0.0594 | 0.9419 | PASS |
| step | hier_ssm | 1 | 2000 | 1901 | -0.0348 | -2.3382 | 109 | 2000 | 0.0545 | 0.0450 | 0.0654 | 0.5217 | PASS |
| step | hier_ssm | 3 | 2000 | 1901 | -0.0442 | -2.3429 | 115 | 2000 | 0.0575 | 0.0477 | 0.0686 | 0.2919 | PASS |
| step | hier_ssm | 5 | 2000 | 1901 | -0.0521 | -2.3468 | 115 | 2000 | 0.0575 | 0.0477 | 0.0686 | 0.2919 | PASS |
| step | hier_ssm | 10 | 2000 | 1901 | -0.0697 | -2.3557 | 117 | 2000 | 0.0585 | 0.0486 | 0.0697 | 0.2343 | PASS |
| step | hier_ssm | 15 | 2000 | 1901 | -0.0892 | -2.3654 | 118 | 2000 | 0.0590 | 0.0491 | 0.0702 | 0.2089 | PASS |
| step | hier_ts | 1 | 2000 | 1901 | -0.0348 | -2.3382 | 109 | 2000 | 0.0545 | 0.0450 | 0.0654 | 0.5217 | PASS |
| step | hier_ts | 3 | 2000 | 1901 | -0.0442 | -2.3429 | 115 | 2000 | 0.0575 | 0.0477 | 0.0686 | 0.2919 | PASS |
| step | hier_ts | 5 | 2000 | 1901 | -0.0521 | -2.3468 | 115 | 2000 | 0.0575 | 0.0477 | 0.0686 | 0.2919 | PASS |
| step | hier_ts | 10 | 2000 | 1901 | -0.0697 | -2.3557 | 117 | 2000 | 0.0585 | 0.0486 | 0.0697 | 0.2343 | PASS |
| step | hier_ts | 15 | 2000 | 1901 | -0.0892 | -2.3654 | 118 | 2000 | 0.0590 | 0.0491 | 0.0702 | 0.2089 | PASS |
| step | adj_cusum | 1 | 2000 | 1901 | 131.4840 | 73.1928 | 112 | 2000 | 0.0560 | 0.0463 | 0.0670 | 0.3960 | PASS |
| step | adj_cusum | 3 | 2000 | 1901 | 130.4170 | 72.6594 | 108 | 2000 | 0.0540 | 0.0445 | 0.0648 | 0.5681 | PASS |
| step | adj_cusum | 5 | 2000 | 1901 | 128.4950 | 71.6987 | 105 | 2000 | 0.0525 | 0.0431 | 0.0632 | 0.7194 | PASS |
| step | adj_cusum | 10 | 2000 | 1901 | 121.6070 | 68.2547 | 113 | 2000 | 0.0565 | 0.0468 | 0.0675 | 0.3589 | PASS |
| step | adj_cusum | 15 | 2000 | 1901 | 116.3930 | 65.6475 | 111 | 2000 | 0.0555 | 0.0459 | 0.0665 | 0.4356 | PASS |
| step | glr_window | 1 | 2000 | 1901 | 53.9994 | 33.0382 | 112 | 2000 | 0.0560 | 0.0463 | 0.0670 | 0.3960 | PASS |
| step | glr_window | 3 | 2000 | 1901 | 51.5059 | 31.7914 | 114 | 2000 | 0.0570 | 0.0472 | 0.0681 | 0.3242 | PASS |
| step | glr_window | 5 | 2000 | 1901 | 49.9939 | 31.0354 | 111 | 2000 | 0.0555 | 0.0459 | 0.0665 | 0.4356 | PASS |
| step | glr_window | 10 | 2000 | 1901 | 47.4035 | 29.7403 | 106 | 2000 | 0.0530 | 0.0436 | 0.0637 | 0.6671 | PASS |
| step | glr_window | 15 | 2000 | 1901 | 45.6097 | 28.8434 | 109 | 2000 | 0.0545 | 0.0450 | 0.0654 | 0.5217 | PASS |

_Summary:_ 50/50 cells pass Gate G2 ($p_{\text{bb}} > 0.001$, minimum $p_{\text{bb}} = 0.1071$). All cells are evaluable.

---

## 2. Hypothesis H1: Hierarchical Pooling Helps

### Preregistered Decision Rule (`docs/PREREGISTRATION_V3.md`):
> Contrast C2 (`hier_ssm` vs `indep_ssm`) at $m=1$ negative with family-wise Holm $p < 0.05$ in $\ge 2$ of `{weak_persistent_3host, class_wide, broad_fleet}`.
> **Cost check:** In `single_host_persistent`, C2 is reported; if `hier_ssm` is slower by $>3$ min or power lower by $>5$ pp, report **"pooling suppresses local faults"**.

### Primary Target Scenarios (Contrast C2 at $m=1$):
| Scenario | Mean Capped Diff (min) | 95% Bootstrap CI | Sign-flip $p$ | Holm $p$ | Criterion ($\text{diff} < 0 \land p_{\text{holm}} < 0.05$) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `class_wide` | -7.803 | [-8.867, -6.847] | 0.0002 | 0.0110 | **MET** |
| `broad_fleet` | -4.523 | [-4.983, -4.077] | 0.0002 | 0.0110 | **MET** |
| `weak_persistent_3host` | -1.317 | [-4.803, 2.514] | 0.4883 | 1.0000 | NOT MET |

### Cost Check Scenario (`single_host_persistent` at $m=1$):
| Scenario | Mean Capped Diff (min) | Sign-flip $p$ | Holm $p$ | `hier_ssm` Power | `indep_ssm` Power | Power Difference |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `single_host_persistent` | +9.460 | 0.0002 | 0.0110 | 0.8733 | 0.9267 | -0.0533 (-5.33 pp) |

### Verdict: **SUPPORTED**
- **Primary condition:** Met in 2 of 3 specified target scenarios (`class_wide` and `broad_fleet`), where hierarchical pooling reduces detection delay by 7.80 min and 4.52 min respectively ($p_{\text{holm}} = 0.0110$).
- **Cost check:** TRIGGERED. In `single_host_persistent`, `hier_ssm` is 9.46 min slower ($>3$ min threshold) and suffers a 5.33 pp power loss ($>5$ pp threshold).
- **Mandatory preregistered statement:** **"Pooling suppresses local faults."**

---

## 3. Hypothesis H2: Two-Scale Cross-Level Inertia Adds Value Beyond Persistence

### Preregistered Decision Rule (`docs/PREREGISTRATION_V3.md`):
> Contrast C1 (`hier_ts` vs `hier_ssm`) at $m=1$ negative with family-wise Holm $p < 0.05$ AND $|\text{diff}| \ge 1$ minute in $\ge 1$ of `{slow_drift_3host, mixed_fast_slow, regression_recovery, partial_recovery, weak_persistent_3host}`; AND in every other event scenario power not lower than `hier_ssm` by $>2$ pp; AND its calibration cell passes.
> If the C1 CI lies within $\pm 1$ minute in all of these $\to$ **NOT SUPPORTED ("no practical difference")**; otherwise **INCONCLUSIVE**.
> Only **SUPPORTED** permits the word "inertia contribution" (Addendum J1).

### Target Scenarios (Contrast C1 at $m=1$):
| Scenario | Mean Capped Diff (min) | 95% Bootstrap CI | Sign-flip $p$ | Holm $p$ | Inside $\pm 1$ min CI? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `slow_drift_3host` | 0.000 | [0.000, 0.000] | 1.0000 | 1.0000 | Yes |
| `mixed_fast_slow` | 0.000 | [0.000, 0.000] | 1.0000 | 1.0000 | Yes |
| `regression_recovery` | 0.000 | [0.000, 0.000] | 1.0000 | 1.0000 | Yes |
| `partial_recovery` | 0.000 | [0.000, 0.000] | 1.0000 | 1.0000 | Yes |
| `weak_persistent_3host` | 0.000 | [0.000, 0.000] | 1.0000 | 1.0000 | Yes |

_Note:_ Under candidate budget parity and nesting verification (`nests_hier_ssm == True`), the CV grid search selected the boundary nested parameterization `prior_h_ratio = 1.0`, `rho = 0.999`, rendering `hier_ts` and `hier_ssm` functionally and numerically identical.

### Verdict: **NOT SUPPORTED ("no practical difference")**
- The confidence intervals for Contrast C1 lie strictly within $[-1.0, +1.0]$ minutes in all 5 target scenarios.
- In accordance with Addendum J1, the term "inertia contribution" is not supported and is not claimed.

---

## 4. Hypothesis H3: Decision Hysteresis Reduces False Pauses

### Preregistered Decision Rule (`docs/PREREGISTRATION_V3.md`):
> For `hier_ssm`, there is an $m > 1$ such that:
> (a) Alert rate on harm rollouts WITHOUT an event (`harm_rollout_noevent_alert_rate`, scenarios `iso_spike_1host` and `short_3host` pooled) falls $\ge 50\%$ relative to $m=1$; AND
> (b) Mean capped time on `weak_persistent_3host` rises $\le 3$ min.

### Evaluation Across $m \in \{1, 3, 5, 10, 15\}$:
| $m$ | `iso_spike_1host` No-Event Alert Rate | `short_3host` No-Event Alert Rate | Pooled No-Event Alert Rate | Relative Change vs $m=1$ | `weak_persistent_3host` Mean Capped Time (min) | Delay Increase vs $m=1$ (min) | Conditions Met? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | 0.2733 | 0.4467 | **0.3600** | Baseline | 37.080 | 0.000 | Baseline |
| **3** | 0.3067 | 0.4267 | **0.3667** | +1.85% (increase) | 37.710 | +0.630 | Fails (a) |
| **5** | 0.2600 | 0.4233 | **0.3417** | -5.09% | 40.370 | +3.290 | Fails (a), Fails (b) |
| **10** | 0.2533 | 0.3867 | **0.3200** | -11.11% | 42.893 | +5.813 | Fails (a), Fails (b) |
| **15** | 0.2367 | 0.3333 | **0.2850** | -20.83% | 44.423 | +7.343 | Fails (a), Fails (b) |

### Verdict: **NOT SUPPORTED**
- A $\ge 50\%$ relative reduction in pooled non-event alert rate would require an alert rate $\le 0.1800$. The maximum observed reduction was only 20.83% at $m=15$ (pooled rate 0.2850).
- Furthermore, at $m \in \{5, 10, 15\}$, the capped detection time on `weak_persistent_3host` increased by 3.29 to 7.34 min, exceeding the 3.0-minute tolerance.

---

## 5. Hypothesis H4: Stability Under Reversible Rollouts (Exploratory / Descriptive)

### Preregistered Decision Rule (`docs/PREREGISTRATION_V3.md`):
> `hier_ts` lowers mean recovery delay vs `hier_ssm` by $\ge 5$ min at $m=1$ in both `regression_recovery` and `partial_recovery`; also report reversals and time paused.

### Summary Metrics at $m=1$:
| Scenario | Method | Mean Recovery Delay (min) | Difference (ts - ssm) | Mean Reversals | Mean Time Paused (min) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `regression_recovery` | `hier_ts` | 64.111 | 0.000 | 1.273 | 103.820 |
| `regression_recovery` | `hier_ssm` | 64.111 | - | 1.273 | 103.820 |
| `partial_recovery` | `hier_ts` | 47.801 | 0.000 | 1.173 | 106.657 |
| `partial_recovery` | `hier_ssm` | 47.801 | - | 1.173 | 106.657 |

### Verdict: **NOT SUPPORTED (no practical difference due to nested parameterization)**

---

## 6. Hypothesis H5: State-Space Models vs Classical Baselines

### Preregistered Decision Rule (`docs/PREREGISTRATION_V3.md`):
> SSM (`hier_ts` or `hier_ssm`) faster than the better of `adj_cusum` and `glr_window` with family-wise Holm $p < 0.05$ in $\ge$ half the event scenarios (6/11) AND slower (Holm $p < 0.05$) in none.

### Comparison Across All 11 Event Scenarios at $m=1$:
| Event Scenario | SSM Capped Time (min) | `adj_cusum` Capped Time | `glr_window` Capped Time | Better Classical Method | Contrast Difference (SSM - Better) | Sign-flip $p$ | Holm $p$ | SSM Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `broad_fleet` | 1.43 | 25.20 | 10.28 | `glr_window` | -8.850 | 0.0002 | 0.0440 | **Faster ($p < 0.05$)** |
| `class_wide` | 3.21 | 38.85 | 19.13 | `glr_window` | -15.923 | 0.0002 | 0.0440 | **Faster ($p < 0.05$)** |
| `mixed_fast_slow` | 32.47 | 47.76 | 38.84 | `glr_window` | -6.377 | 0.0002 | 0.0440 | **Faster ($p < 0.05$)** |
| `partial_recovery` | 10.98 | 37.15 | 23.58 | `glr_window` | -12.593 | 0.0002 | 0.0440 | **Faster ($p < 0.05$)** |
| `periodic_workload` | 18.88 | 56.24 | 32.57 | `glr_window` | -13.693 | 0.0002 | 0.0440 | **Faster ($p < 0.05$)** |
| `regression_recovery` | 11.34 | 34.43 | 21.23 | `glr_window` | -9.890 | 0.0002 | 0.0440 | **Faster ($p < 0.05$)** |
| `single_host_persistent` | 30.89 | 50.76 | 61.60 | `adj_cusum` | -19.870 | 0.0002 | 0.0440 | **Faster ($p < 0.05$)** |
| `weak_persistent_3host` | 37.08 | 78.79 | 58.39 | `glr_window` | -21.310 | 0.0002 | 0.0440 | **Faster ($p < 0.05$)** |
| `workload_spikes` | 22.53 | 57.00 | 36.13 | `glr_window` | -13.600 | 0.0002 | 0.0440 | **Faster ($p < 0.05$)** |
| `slow_drift_3host` | 49.86 | 36.34 | 30.29 | `glr_window` | +19.577 | 0.0002 | 0.0440 | **Slower ($p < 0.05$)** |
| `step_plus_harm` | 108.56 | 119.74 | 93.69 | `glr_window` | +14.873 | 0.0002 | 0.0440 | **Slower ($p < 0.05$)** |

### Verdict: **NOT SUPPORTED (Partially Favored: Faster in 9/11 scenarios, but significantly slower in 2/11)**
- SSM is significantly faster than the best classical baseline in 9 of 11 event scenarios (exceeding the 6/11 requirement).
- However, SSM is significantly slower with Holm $p < 0.05$ in 2 scenarios (`slow_drift_3host` by +19.58 min, `step_plus_harm` by +14.87 min).
- Because the preregistered rule requires "slower in none", H5 cannot be claimed as SUPPORTED.

---

## 7. Runtime Benchmarking (`table_runtime.csv`)

Measured mean single-step update latency per host-group across test rollouts:

| Method Family | Mean Update Time (ms) | Relative to Fastest |
| :--- | :--- | :--- |
| `adj_cusum` | 0.0105 ms | $1.0\times$ (Fastest) |
| `glr_window` | 0.1286 ms | $12.3\times$ |
| `hier_ssm` | 0.4240 ms | $40.5\times$ |
| `hier_ts` | 0.4242 ms | $40.5\times$ |
| `indep_ssm` | 0.4250 ms | $40.6\times$ |

All SSM Kalman filter updates execute in approximately 0.42 ms per host-group step on CPU, remaining orders of magnitude below the 1-minute telemetry collection interval.

---

## 8. Summary of Preregistered Research Hypotheses

| Hypothesis | Topic | Preregistered Verdict | Quantitative Basis |
| :--- | :--- | :--- | :--- |
| **H1** | Hierarchical Pooling | **SUPPORTED** | Faster in `class_wide` (-7.80 min) and `broad_fleet` (-4.52 min), $p_{\text{holm}} = 0.0110$. **Cost check triggered:** Slower by 9.46 min and power reduced by 5.33 pp in `single_host_persistent`. Mandatory statement: *"Pooling suppresses local faults."* |
| **H2** | Two-Scale Cross-Level Inertia | **NOT SUPPORTED** | Mean difference 0.000 min, 95% CI $[0.000, 0.000] \subset [-1.0, 1.0]$ in all 5 target scenarios. Nested parameter asymptote selected (`prior_h_ratio=1.0`). |
| **H3** | Decision Hysteresis | **NOT SUPPORTED** | Non-event alert rate on `{iso_spike, short}` reduced by at most 20.8% ($m=15$), failing the 50% relative reduction threshold; capped time on `weak_persistent` increased by 7.34 min ($>3.0$ min). |
| **H4** | Stability (Exploratory) | **NOT SUPPORTED** | Recovery delay difference 0.000 min in both `regression_recovery` and `partial_recovery` due to nested parameter equivalence. |
| **H5** | Classical Comparator | **NOT SUPPORTED** | Faster than classical baselines in 9 of 11 event scenarios ($p_{\text{holm}} < 0.05$), but significantly slower in 2 scenarios (`slow_drift_3host`, `step_plus_harm`). "Slower in none" criterion failed. |
