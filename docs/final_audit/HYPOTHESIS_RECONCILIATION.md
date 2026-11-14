# Preregistration and Hypothesis Consistency Audit Report
**Canary SSM V3 — Research & Release Verification**

- **Date:** 2026-11-14
- **Governing Preregistration:** `docs/PREREGISTRATION_V3.md` (Frozen at Phase 3 inception)
- **Companion Specifications:** `docs/ANTIGRAVITY_SPEC_V3.md`, `docs/Canary_SSM_Change_Plan.pdf` (Rev 3)
- **Primary Contrast Evidence:** `results/study_inertia/table_paired_contrasts.csv` (N = 550 contrast tests)
- **Scenario Summary Evidence:** `results/study_inertia/table_scenario_summary.csv` (N = 400 scenario-method cells)

---

### 1. Executive Summary & Audit Context

A comprehensive audit was performed comparing the frozen preregistration definitions against the terminology, definitions, and conclusions reported across the Stage 1, Stage 2, and Stage 3 completion reports.

Key findings of this audit:
1. **Mathematical Invariance:** The underlying statistical calculations, paired sign-flip permutation tests (5,000 permutations), and Holm-adjusted family-wise $p$-values computed in `table_paired_contrasts.csv` were executed strictly according to the frozen protocol.
2. **Terminology Drift in Stage 3 Narrative:** In the Stage 3 narrative report, H1 was informally described as "Detection Delay Reduction" (emphasizing the $-2.53\text{ min}$ advantage over unpooled models) rather than "Hierarchical Pooling", and H4 was described as "Single-Host Anomaly Sensitivity" rather than the exploratory "Recovery Stability". 
3. **Reconciliation with Preregistered Text:** The Stage 3 "Single-Host Sensitivity" finding is actually the explicit **cost-check clause** of H1 specified in `docs/PREREGISTRATION_V3.md` ("in `single_host_persistent` C2 is reported; if `hier_ssm` is slower by >3 min or power lower by >5 pp, report 'pooling suppresses local faults'"). In `single_host_persistent`, `hier_ssm` was slower by **+9.46 min**, triggering the mandatory cost-check report. Meanwhile, the original exploratory H4 (requiring $\ge 5\text{ min}$ recovery delay reduction in `regression_recovery` and `partial_recovery`) yielded a difference of $0.00\text{ min}$ and is **NOT SUPPORTED**.
4. **Primary Research Claim:** The only hypothesis meeting the preregistered criteria for **SUPPORTED** is **H1** (Hierarchical pooling provides a statistically significant detection speedup on fleet events with Holm $p < 0.05$ in $\ge 2$ core fleet scenarios, with the mandatory cost caveat that pooling suppresses localized single-host defects).

---

### 2. Complete Hypothesis Reconciliation Matrix

| Preregistered Hypothesis (`PREREGISTRATION_V3.md`) | Stage 2 Definition & Result | Stage 3 Definition & Result | Authoritative Evidence Files | Final Rigorous Interpretation |
| :--- | :--- | :--- | :--- | :--- |
| **H1: Pooling Benefit & Cost Check**<br>C2 (`hier_ssm` vs `indep_ssm`) at $m=1$ negative with Holm $p < 0.05$ in $\ge 2$ of `{weak_persistent_3host, class_wide, broad_fleet}`.<br>*Cost check:* in `single_host_persistent`, if slower by $>3$ min or power lower by $>5$ pp, report "pooling suppresses local faults". | **"Hierarchical Pooling"**<br>SUPPORTED.<br>C2 negative and significant in `broad_fleet` ($\Delta = -5.39$ min, $p = 0.011$) and `class_wide` ($\Delta = -4.82$ min, $p = 0.011$). Cost check noted in `single_host_persistent` ($+9.46$ min). | **"Detection Delay Reduction"**<br>SUPPORTED.<br>Emphasized detection speed advantage: $-2.53$ min (95% CI $[-3.98, -0.99]$, $p = 0.0012$) over unpooled models. | `results/study_inertia/table_paired_contrasts.csv` (rows with `hypothesis == "H1"`)<br>`results/plain_final/table_detection.csv` | **CONFIRMATORY SUPPORTED (with mandatory cost finding)**.<br>Preregistered threshold met: Holm $p < 0.05$ in 2 of 3 designated scenarios. The cost check is triggered: hierarchical shrinkage delays localized single-host defect detection by $+9.46\text{ min}$. |
| **H2: Two-Scale Cross-Level Inertia**<br>C1 (`hier_ts` vs `hier_ssm`) at $m=1$ negative with Holm $p < 0.05$ AND $\|\text{diff}\| \ge 1$ min in $\ge 1$ event scenario, power drop $\le 2$ pp.<br>*If CI within $\pm 1$ min everywhere $\to$ NOT SUPPORTED.* | **"Cross-Level Inertia"**<br>NOT SUPPORTED.<br>C1 differences were $0.00$ to $-0.18$ min; 95% CIs fell entirely within $\pm 1$ min across all event scenarios. | **"Two-Scale Inertia Benefit"**<br>NOT SUPPORTED.<br>No statistically significant advantage ($\Delta = -0.18$ min, $p = 0.42$). | `results/study_inertia/table_paired_contrasts.csv` (rows with `hypothesis == "H2"`) | **CONFIRMATORY NOT SUPPORTED**.<br>0 of 55 H2 contrast tests reached significance (all Holm $p = 1.0$). C1 CI lies within $\pm 1\text{ min}$ in all event scenarios. Per Addendum J1, the term "inertia contribution" is prohibited. |
| **H3: Decision Hysteresis**<br>For `hier_ssm`, $\exists m > 1$ such that false pauses on non-events (`iso_spike_1host`, `short_3host`) fall $\ge 50\%$ relative to $m=1$, AND capped delay on `weak_persistent_3host` rises $\le 3$ min. | **"Decision Hysteresis"**<br>NOT SUPPORTED.<br>While false alarms fell on isolated spikes, detection delay on `weak_persistent_3host` rose by $>3$ min at $m=3,5$ ($+4.12$ min at $m=3$). | **"Hysteresis False Alarm Reduction"**<br>NOT SUPPORTED.<br>Hysteresis thresholds did not achieve statistically superior false-alarm control over single-threshold replay calibration. | `results/study_inertia/table_paired_contrasts.csv` (rows with `hypothesis == "H3"`)<br>`results/study_inertia/table_scenario_summary.csv` | **CONFIRMATORY NOT SUPPORTED**.<br>The dual condition (50% false pause reduction with $\le 3$ min detection delay penalty) failed. Increasing $m$ introduced excessive delay penalty on weak persistent signals. |
| **H4: Exploratory Recovery Stability**<br>Descriptive: `hier_ts` lowers mean recovery delay vs `hier_ssm` by $\ge 5$ min at $m=1$ in `regression_recovery` and `partial_recovery`; also report reversals and time paused. | **"Recovery Stability"**<br>NOT SUPPORTED.<br>Recovery delay was identical ($0.00$ min difference) between `hier_ts` and `hier_ssm` ($103.82$ min vs $103.82$ min). | **"Single-Host Anomaly Sensitivity"**<br>NOT SUPPORTED.<br>Reflected H1 cost check: shrinkage delayed localized detection by $+9.46$ min. | `results/study_inertia/table_scenario_summary.csv` (scenarios `regression_recovery`, `partial_recovery`) | **EXPLORATORY NOT SUPPORTED**.<br>Under the original recovery definition, `hier_ts` did not reduce recovery delay by $\ge 5$ min ($\Delta = 0.00$ min). Under the Stage 3 single-host framing, localized sensitivity was similarly penalized. |
| **H5: Classical Comparator Dominance**<br>SSM faster than better of `adj_cusum`/`glr_window` with Holm $p < 0.05$ in $\ge$ half event scenarios and slower in none. | **"Classical Comparator"**<br>NOT SUPPORTED.<br>While SSM was substantially faster in fleet scenarios (e.g. `broad_fleet`, `class_wide`), GLR performed comparably on clean steps and localized faults. | **"Unilateral Classical Dominance"**<br>NOT SUPPORTED.<br>SSM does not unilaterally dominate classical methods across every operational regime. | `results/study_inertia/table_paired_contrasts.csv` (rows with `hypothesis == "H5"`) | **CONFIRMATORY NOT SUPPORTED**.<br>Although SSM is faster in 8 of 16 scenarios ($p < 0.05$), it is significantly slower in `single_host_persistent` compared to unpooled GLR/CUSUM, violating the "slower in none" criterion. |

---

### 3. Categorization of Research Findings

Under the governing scientific protocol, project findings are formally categorized as:

#### 3.1 Preregistered Confirmatory Findings
- **H1 Supported (Fleet Event Speedup):** Hierarchical state-space modeling reduces detection delay on correlated fleet disturbances by an average of $2.53\text{ min}$ over unpooled models ($p < 0.002$) and over $17\text{ min}$ over sequential GLR.
- **H1 Cost Confirmed (Localized Shrinkage Penalty):** When an anomaly is confined to a single canary instance, hierarchical pooling imposes a $+9.46\text{ min}$ detection penalty because group-level states shrink the isolated signal toward zero.
- **H2 Rejection (Two-Scale Dynamics):** Class-level inertia states offer no statistically detectable advantage over single-scale fleet state-space filtering ($p = 1.00$).
- **H3 Rejection (Decision Hysteresis Trade-off):** Increasing consecutive confirmation steps $m$ suppresses transient spikes but degrades time-to-rollback on gradual or weak anomalies beyond the 3-minute tolerance.
- **H5 Rejection (No Universal Dominance):** Classical sequential detectors remain competitive in clean, single-node or step-jump settings with lower computational complexity.

#### 3.2 Held-Out Test Confirmation (Phase 4)
- Generalization of calibrated false-alert rates on completely unseen synthetic data verified Gate G2 validity: **3.80%** (Plain Test) and **4.10%** (Step Test).
- Mean capped detection times on test data confirmed the primary hierarchy advantage: **15.57 min** (`hier_ssm`) vs **18.10 min** (`indep_ssm`) vs **33.38 min** (`glr_window`) vs **44.16 min** (`adj_cusum`).

#### 3.3 Exploratory & Robustness Findings (Phase 5)
- Under heavy-tailed measurement noise ($t(3)$), Kalman observation updates provide strong robustness (false alarms bounded at 6.0%, power 99.67%), whereas memoryless GLR false alarms explode to 85.7%.
- Under 20% random telemetry dropout, state-space propagation maintains detection delay within $18.42\text{ min}$, whereas windowed baselines degrade significantly.

---

### 4. Integrity Verdict

The preregistered definitions from `docs/PREREGISTRATION_V3.md` are the single source of truth. All retrospective narrative summaries must adhere strictly to the designations in this audit.
