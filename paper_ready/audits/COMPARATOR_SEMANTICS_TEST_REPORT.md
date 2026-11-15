# COMPARATOR SEMANTICS TEST REPORT: FIXTURES KAY-01 THROUGH COMMON-01

- **Document Version**: 1.0
- **Execution Date**: 2026-11-15
- **Test File**: `tests/test_comparator_semantics.py`
- **Pytest Exit Code**: 0 (8 passed in 0.73s)
- **Governing Specification**: Supplemental Addendum (Section B)

---

## 1. Test Execution Dashboard

| Fixture ID | Test Function | Target Semantic Rule | Expected Output | Observed Output | Status |
|---|---|---|---|---|---|
| **KAY-01** | `test_kay_01_mann_whitney_u_and_direction` | Non-parametric Mann-Whitney U & direction | $U$-stat matches SciPy, $p < 0.05$, $z > 0$, outcome `FAIL_CRITICAL` | $U=36.0, p=0.00108, z=3.04$, `FAIL_CRITICAL` | **PASSED** |
| **KAY-02** | `test_kay_02_ties_and_insufficient_samples` | Tie handling & minimum sample enforcement | Samples $< 5 \implies \text{NODATA}$; all ties $\implies \text{PASS}$; NaNs filtered | Returns `NODATA` ($p=1.0$), `PASS` on ties, NaNs filtered cleanly | **PASSED** |
| **ARGO-01** | `test_argo_01_deterministic_failure_limit_trace` | AR-3 failureLimit & consecutive mode | Monotonic counter progression; resets on pass if consecutive | Exact score sequence $[0, 1/3, 1/3, 2/3, 1.0]$; consecutive resets to 0 | **PASSED** |
| **ARGO-02** | `test_argo_02_missing_and_error_handling` | Inconclusive & missing data policy | NaNs do not increment failure counter or corrupt state | NaNs treated as neutral; state retained | **PASSED** |
| **FLAG-01** | `test_flag_01_step_progression_and_threshold` | Cumulative failure budget (maxFailedChecks=5) | Breaches at 5 failures ($5/5 = 1.0$); triggers rollback | Score $[1/5, 2/5, 2/5, 3/5, 4/5, 1.0, 1.0]$; breach confirmed | **PASSED** |
| **FLAG-02** | `test_flag_02_cumulative_failure_retention_on_recovery` | Cumulative retention across clean checks | Counter does NOT reset on subsequent passes | Score remains $2/5 = 0.4$ across clean checks | **PASSED** |
| **SLO-01** | `test_slo_01_boundary_and_window_averaging` | Contrast delta boundary & window averaging | Strict threshold comparison; 2m rolling mean | Exact sequence $[-1.0, 0.0, 2.0, 4.0]$ matches manual derivation | **PASSED** |
| **COMMON-01**| `test_common_01_streaming_prefix_invariance` | Causal streaming prefix invariance | Scores at $t$ invariant to future data arrivals | Absolute error $< 10^{-15}$ across all cutoffs $t \in \{7, 10, 14\}$ | **PASSED** |

---

## 2. Deterministic State Trace Derivations

### A. ARGO-01: AR-3 Cumulative and Consecutive Traces
Under test signal $\mathbf{z} = [0, 1, 0, 1, 1, 0]$ with $t_0 = 2$ and $\text{failureLimit} = 3$:
- $t=2: z=0 \implies C=0 \implies S = 0.0$
- $t=3: z=1 \implies C=1 \implies S = 1/3 \approx 0.3333$
- $t=4: z=0 \implies C=1 \implies S = 1/3 \approx 0.3333$ (cumulative) vs $C=0 \implies S=0.0$ (consecutive reset)
- $t=5: z=1 \implies C=2 \implies S = 2/3 \approx 0.6667$ (cumulative) vs $C=1 \implies S=0.3333$ (consecutive)
- $t=6: z=1 \implies C=3 \implies S = 3/3 = 1.0$ (cumulative **BREACH**) vs $C=2 \implies S=0.6667$ (consecutive)

### B. FLAG-01: Flagger Cumulative Failure Budget
Under test signal $\mathbf{z} = [1, 1, 0, 1, 1, 1]$ with $\text{maxFailedChecks} = 5$:
- Increments at $t \in \{1, 2, 4, 5, 6\}$, reaching $5/5 = 1.0$ at $t=6$. Subsequent clean checks at $t=7$ retain the budget exhaustion state ($1.0$), ensuring latched rollback.

### C. SLO-01: Contrast Window Derivation
Canary $\mathbf{r}_{\text{can}} = [0, 0, 0, 2, 4, 6]$, Control $\mathbf{r}_{\text{ctl}} = [1, 1, 1, 1, 1, 1]$, Window $W=2$:
- $t=2: \text{win}[1..2] \implies \bar{r}_{\text{can}} = 0.0, \bar{r}_{\text{ctl}} = 1.0 \implies \Delta = -1.0$
- $t=3: \text{win}[2..3] \implies \bar{r}_{\text{can}} = 1.0, \bar{r}_{\text{ctl}} = 1.0 \implies \Delta = 0.0$
- $t=4: \text{win}[3..4] \implies \bar{r}_{\text{can}} = 3.0, \bar{r}_{\text{ctl}} = 1.0 \implies \Delta = +2.0$
- $t=5: \text{win}[4..5] \implies \bar{r}_{\text{can}} = 5.0, \bar{r}_{\text{ctl}} = 1.0 \implies \Delta = +4.0$
Matches theoretical values exactly.
