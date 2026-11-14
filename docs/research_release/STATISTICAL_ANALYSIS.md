# Statistical Analysis: Canary SSM V3
## Hierarchical, Inertia-Constrained State-Space Models for Safer Software Rollout Decisions

- **Inference Standards:** Exact Finite-Sample Calibration, Paired Permutation Tests, Bootstrap Uncertainty, and Multiplicity Correction
- **Governing Protocol:** `docs/PREREGISTRATION_V3.md` & `docs/Canary_SSM_Change_Plan.pdf` (Revision 3)

---

### 1. Sample Size Determination & Statistical Power

To eliminate pilot-study power deficiencies identified in previous research iterations (Lesson 9), sample sizes were scaled to guarantee high statistical power:

| Experimental Partition | Sample Size | Primary Statistical Objective | Mathematical Guarantee |
| :--- | :---: | :--- | :--- |
| **Calibration Set** | $B = 2,000$ nulls | Order-statistic threshold estimation ($\tau_{\text{high}}$) | Standard error of empirical quantile $\approx \sqrt{\alpha(1-\alpha)/B} \approx 0.0049$ |
| **Null Validation Set** | $n = 2,000$ nulls | Exchangeability and Gate G2 validity test | Detects false-alert rate shifts from 5.0% to 7.0% with $>95\%$ power |
| **Inertia Study Evaluation** | 300 pairs $\times$ 16 scenarios = 9,600 rollouts | Paired contrast testing across 16 scenarios (240,000 policy instances) | Detects paired detection delay differences $\|\Delta\| \ge 1.0\text{ min}$ with $>90\%$ power |
| **Final Test Evaluation** | 1,000 pairs (2,000 rollouts) per regime | Generalization audit on held-out test data | Narrow 95% Clopper-Pearson CI width on FAR $\le 2.5\text{ pp}$ |

---

### 2. Paired Experimental Design & The Sign-Flip Permutation Test

#### 2.1 Paired Design Rationale
In canary telemetry benchmarking, rollout-level variance (random traffic surges, background batch jobs, diurnal phases) dwarfs the variance between competitive algorithms. To eliminate inter-rollout variance, every detector method is evaluated on the **exact same simulated rollout stream** sharing identical random seeds.

#### 2.2 Paired Differences
For a given scenario and contrast pair (e.g., $A = \text{hier\_ssm}$ vs $B = \text{indep\_ssm}$):
$$d_j = T_{\text{capped}, j}^{(A)} - T_{\text{capped}, j}^{(B)}, \quad j \in \{1, \dots, N_{\text{harm}}\}$$
A negative difference ($d_j < 0$) indicates that Method A detected the anomaly faster or avoided a miss.

#### 2.3 Two-Sided Sign-Flip Permutation Test
Under the null hypothesis of no difference between detectors ($H_0: d_j \stackrel{d}{=} -d_j$):
1. Compute the observed test statistic: $\bar{d} = \frac{1}{N} \sum_{j=1}^N d_j$.
2. For $p \in \{1, \dots, 5000\}$ permutations:
   - Sample independent Rademacher variables $s_{j}^{(p)} \in \{-1, +1\}$ with equal probability.
   - Form the permuted mean: $\bar{d}^{(p)} = \frac{1}{N} \sum_{j=1}^N s_j^{(p)} d_j$.
3. The exact two-sided permutation $p$-value is:
   $$p_{\text{signflip}} = \frac{1}{5000} \sum_{p=1}^{5000} \mathbb{I}\left(|\bar{d}^{(p)}| \ge |\bar{d}|\right)$$

---

### 3. Family-Wise Error Rate & Holm Multiplicity Correction

Because 550 contrast tests were conducted across the study matrix, uncontrolled testing would result in massive false discovery inflation.

In accordance with Blocker B4 resolution:
- Contrast rows in `table_paired_contrasts.csv` are grouped strictly by **hypothesis family** ($\mathcal{H} \in \{\text{H1}, \text{H2}, \text{H3}, \text{H5}\}$).
- The Holm-Bonferroni step-down procedure is applied within each family:
  1. Sort unadjusted $p$-values: $p_{(1)} \le p_{(2)} \le \dots \le p_{(M)}$.
  2. Adjusted $p$-values are computed sequentially:
     $$\tilde{p}_{(i)} = \min\left(1.0, \max\left(\tilde{p}_{(i-1)}, (M - i + 1) \cdot p_{(i)}\right)\right)$$
  3. Significance is declared if $\tilde{p}_{(i)} < 0.05$.

---

### 4. Uncertainty Intervals: Clopper-Pearson & Paired Bootstrap

#### 4.1 Exact Clopper-Pearson Confidence Intervals (Rates)
For false-alert rates and miss rates ($k$ events in $n$ trials), normal approximations fail near boundary regions ($\alpha = 0.05$). Exact Clopper-Pearson binomial intervals are used:
$$\text{CI}_{\text{lower}} = B\left(\frac{\alpha_{\text{ci}}}{2}; k, n - k + 1\right), \quad \text{CI}_{\text{upper}} = B\left(1 - \frac{\alpha_{\text{ci}}}{2}; k + 1, n - k\right)$$
where $B(q; a, b)$ is the $q$-th quantile of the Beta distribution.

#### 4.2 Paired Bootstrap Confidence Intervals (Delay Differences)
Confidence intervals for mean capped delay differences $\bar{d}$ are constructed via 1,000 paired bootstrap resamples:
1. Resample indices $j^* \in \{1, \dots, N\}$ with replacement.
2. Compute resampled mean $\bar{d}^* = \frac{1}{N} \sum d_{j^*}$.
3. Construct the 95% interval using the 2.5th and 97.5th percentiles of the bootstrap distribution.

---

### 5. Finite-Sample Order-Statistic Calibration & Gate G2

Threshold calibration uses order statistics on $B = 2,000$ exchangeable null rollouts:
$$k_{\text{order}} = \lceil (1 - \alpha)(B + 1) \rceil = \lceil 0.95 \times 2001 \rceil = 1,901$$
On independent validation nulls ($n = 2,000$), the number of false alarms $K_{\text{val}}$ follows the Beta-Binomial distribution:
$$K_{\text{val}} \sim \text{BetaBinomial}(n, B + 1 - k + 1, k) = \text{BetaBinomial}(2000, 101, 1901)$$
The exact two-sided Beta-Binomial $p$-value tests whether the validation false-alarm count is consistent with exchangeability:
- **Gate G2 Requirement:** $p \ge 0.01$ and achieved rate $\le 0.075$.
- Primary study achieved $p \in [0.107, 1.000]$ across all 50 cells.

---

### 6. Rigorous Interpretation of Negative Findings

In modern empirical science, negative findings are primary experimental results:
- **H2 (Two-Scale Inertia):** The confidence intervals for the C1 contrast fell entirely within the $[-1.0, +1.0]\text{ minute}$ boundary of practical equivalence across all event scenarios. This proves an empirical equivalence: two-scale class dynamics provide no measurable benefit over fleet-level filtering.
- **H3 (Hysteresis Trade-off):** Demonstrates an inescapable operating boundary: confirmation depth $m > 1$ reduces false pauses on isolated spikes, but delays detection of gradual harm beyond acceptable thresholds ($>3\text{ min}$).
- **H5 (No Classical Dominance):** Confirms that classical detectors (GLR, CUSUM) remain computationally superior choices in unconfounded, high-signal, single-node environments.
