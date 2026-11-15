# Statistical Protocol: Data Roles, Variance Matching, Abstention, and Covariance

**Version:** 1.0.0  
**Governing Standard:** `docs/Canary_SSM_Change_Plan.pdf` (Revision 3), `AGENTS.md`, and `docs/DESIGN_DECISIONS.md`.

This document specifies the strict methodological protocol for the `canary_ssm` system across four areas:
1. Four-Role Data Protocol & Leakage Prevention
2. Variance-Matched Hierarchical vs. Independent Model Comparisons
3. Order-Statistic Calibration & Ineligible Abstention Reporting
4. Exact Nested Rack Nuisance Estimation & Error Covariance Closed Form

---

## 1. Four-Role Data Partition Protocol

To prevent information leakage, overfitting, and data snooping, all simulation, estimation, calibration, and evaluation workflows must strictly partition data into four disjoint roles.

| Role | Purpose | Operations Allowed | Forbidden Operations | Seed Range (Base) |
|---|---|---|---|---|
| **`dev`** | Model fitting & hyperparameter selection | Estimating pre-period nuisance parameters ($\hat{\mu}_i, \hat{\beta}_i, \hat{\lambda}_i, \hat{\Phi}_e, \hat{\Sigma}_e$); two-fold cross-validation by rollout pair ID; grid search over $(\rho_g, \sigma_g, \text{prior\_sd})$ maximizing capped time-to-success. | Threshold calibration; reporting final benchmark metrics; claims of fleet-wide false-alert rates. | `1,000,000+` |
| **`calibration`** | Threshold setting | Calibrating empirical detection thresholds $h$ on null rollouts under declared false-alert budget $\alpha$ ($k = \lceil(B+1)(1-\alpha)\rceil$); episode replay for persistence/hysteresis policies. | Tuning model hyperparameters; re-estimating nuisance parameters; inspecting harm rollouts. | `2,000,000+` |
| **`null_validation`** | Calibration audit | Exact Beta-Binomial validity gate (Gate G2: $B \ge 2000, n \ge 2000$); checking empirical false alert rate $\hat{\alpha} \le \alpha$. | **NEVER tuned upon.** If a policy fails null validation, the policy is rejected. Re-tuning on null validation is an immediate protocol breach. | `3,000,000+` |
| **`test`** | Final benchmark evaluation | Computing evaluation metrics: capped time-to-success, localization AUC/F1, Brier score, missed detection rates, attribution accuracy under frozen policies. | Any modification of thresholds, hyperparameters, preprocessing, or detector code. Unsealed only after calibration freeze. | `4,000,000+` |

### Hard Rules on Data Separation
- **Disjoint Seed Blocks:** Seed ranges are separated by strides of at least $1,000,000$ (smoke: $10,000$, dev: $1,000,000$, calibration: $2,000,000$, null_validation: $3,000,000$, test: $4,000,000$, audit: $6,000,000$). Verified by `verify_seed_separation()`.
- **Evaluator Firewall:** Detector code (`canary_ssm/factor.py`, `canary_ssm/kalman.py`, `canary_ssm/hierarchy.py`, `canary_ssm/decision.py`, `canary_ssm/detectors.py`, `canary_ssm/detector_service.py`) must **NEVER** import `simulate.Truth`, `canary_ssm.metrics`, or read `*_truth` files.
- **Causality:** At time tick $t$, scores and state estimates may only consume observations with $\text{arrival\_time} \le t$. Baseline parameters $\hat{\mu}_i, \hat{\beta}_i, \hat{\lambda}_i$ must be estimated strictly from pre-period ticks $t < t_0$.

---

## 2. Variance-Matched Hierarchical vs. Independent Model Comparisons

### The Fairness Defect in Legacy Comparisons
In `canary_ssm/hierarchy.py`, the state decomposition decomposes host effect $a_{it}$ into class effect $\theta_{g(i), t}$ and within-class deviation $(B b_t)_i$:
$$a_t = C \theta_t + B b_t$$
where $C \in \mathbb{R}^{n \times G}$ is the class incidence matrix and $B = \text{blockdiag}(B_1, \dots, B_G) \in \mathbb{R}^{n \times (n-G)}$ is the orthonormal within-class Helmert basis ($B^T B = I_{n-G}, C^T B = \mathbf{0}$).

Under the prior and transition noise:
$$\theta_{g, 0} \sim \mathcal{N}(0, \sigma_{\text{prior}}^2), \quad w_{\theta, g, t} \sim \mathcal{N}(0, \sigma_g^2)$$
$$b_{k, 0} \sim \mathcal{N}(0, \sigma_{\text{prior}, b}^2), \quad w_{b, k, t} \sim \mathcal{N}(0, \sigma_h^2)$$
with ratio $\tau = \sigma_h / \sigma_g = \text{sd\_h\_ratio}$.

Because $B_g$ is an orthonormal basis for the orthogonal complement of the all-ones vector in $\mathbb{R}^{m_g}$, the projection $(B_g B_g^T)_{ii} = \frac{m_g - 1}{m_g}$. Consequently, the induced marginal host variance is:
$$\text{Var}(a_{it}) = \text{Var}(\theta_{g(i), t}) + (B_g \text{Var}(b_t) B_g^T)_{ii} = \sigma_g^2 + \sigma_h^2 \frac{m_g - 1}{m_g} = \sigma_g^2 \left( 1 + \tau^2 \frac{m_g - 1}{m_g} \right)$$

In legacy implementations, with $\tau = 1.0$ and $m_g = 6$ hosts per class:
$$\text{Var}(a_{it}) = \sigma_g^2 \left( 1 + \frac{5}{6} \right) = \frac{11}{6} \sigma_g^2 \approx 1.833 \, \sigma_g^2$$
Similarly, when prior covariance $P_{0, b} = \sigma_{\text{prior}}^2 I$, the prior marginal host variance is $1.833 \, \sigma_{\text{prior}}^2$, whereas an independent host model has marginal variance $\sigma_g^2$ and prior $\sigma_{\text{prior}}^2$.

**Fairness Consequence:** Legacy comparisons between hierarchical and independent models conflated shrinkage/pooling benefits with an artificially inflated prior and process variance (~83% larger in the hierarchical filter).

### The Variance-Matched Solution
To isolate pooling and within-class correlation from marginal scale effects, we introduce opt-in variance matching:

1. **Prior Mode (`prior_mode: "ratio_scaled"`):**
   $$P_{0, b} = (\sigma_{\text{prior}} \cdot \tau)^2 I_{n-G}$$
   ensuring prior deviations scale consistently with transition innovation ratios.

2. **Variance-Matched Mode (`variance_mode: "matched"` or `"variance_matched"`):**
   We rescale the class and within-class noise scales by factor $c_g$:
   $$c_g = \frac{1}{\sqrt{1 + \tau^2 \frac{m_g - 1}{m_g}}}$$
   $$\tilde{\sigma}_g = c_g \sigma_g, \quad \tilde{\sigma}_h = c_g \sigma_h = c_g \tau \sigma_g$$
   $$\tilde{\sigma}_{\text{prior}, g} = c_g \sigma_{\text{prior}}, \quad \tilde{\sigma}_{\text{prior}, b} = c_g \tau \sigma_{\text{prior}}$$

Under this scaling, the marginal host prior and process variances equal the independent model's exactly:
$$\text{diag}(\text{Cov}_{\text{hier}}(a)) = \text{diag}(\text{Cov}_{\text{indep}}(a)) = \sigma_g^2 I$$
leaving the within-class correlation structure:
$$\rho_{\text{pool}} = \frac{1}{1 + \tau^2 \frac{m_g - 1}{m_g}}$$
as the sole difference between hierarchical and independent detectors.

### Hyperparameter Grid Constraint (`configs/grids_v3.yaml`)
To prevent unbounded random walks and uncalibrated healthy drift, all grids must satisfy the long-run standard deviation bound (`AGENTS.md` Rule 8):
$$\frac{\sigma_g}{\sqrt{1 - \rho_g^2}} \le \kappa_{\text{harm}} = \log(1.02) \approx 0.0198$$
In `configs/grids_v3.yaml`:
- `sd_h_ratio` is restricted to $\{0.25, 0.5, 1.0\}$.
- The total effective candidate count after filtering is strictly $\le 24$ per model family (hierarchical: 18, independent: 18, pooled: 18, cusum: 12, ewma: 12).
- Candidate counts are permanently logged in `model_config.json`.

---

## 3. Order-Statistic Calibration & Ineligible Abstention Reporting

### Exact Quantile Rule on Finite Null Maxima
For an empirical false-alert budget $\alpha \in (0, 1)$ over $B$ exchangeable null rollouts, the simple first-crossing detection threshold $h$ is calibrated on full-horizon rollout maximum scores:
$$M_b = \max_{t_0 \le t \le T} S_{b, t}, \quad b = 1, \dots, B$$
using the $(1 - \alpha)$ order statistic:
$$k = \lceil (B + 1)(1 - \alpha) \rceil$$
$$h = M_{(k)}$$
Under the decision rule $\text{Alarm}_t \iff S_t > h$, the expected false alert probability is bounded by $\alpha$.

### Abstention Handling Standards
When telemetry coverage falls below operational thresholds ($\le 80\%$ of canaries observed, $< 3$ fresh controls per class, or missing rack controls in nested adjustment), the detector cannot evaluate host effects and must abstain (`eligible=False`, `decision_obs=False`).

In rollouts where **all** evaluation ticks are ineligible, the rollout maximum score is mathematically undefined ($M_b = -\infty$).

**The Corruption Problem:** Treating $-\infty$ as a standard numeric sample in order statistic ranking inflates the effective sample size $B$, depressing $h$ and corrupting the calibrated false-alert rate.

**The Mandatory Protocol (`canary_ssm/decision.py`):**
1. Filter null rollouts to finite maxima:
   $$\mathcal{M}_{\text{finite}} = \{ M_b \mid M_b > -\infty, M_b \text{ is finite} \}$$
2. Explicitly count ineligible episodes:
   $$n_{\text{no\_eligible}} = B - |\mathcal{M}_{\text{finite}}|$$
3. Require sufficient valid nulls:
   $$|\mathcal{M}_{\text{finite}}| \ge \text{min\_B\_for\_alpha}(\alpha) = \left\lceil \frac{1 - \alpha}{\alpha} \right\rceil$$
   If $|\mathcal{M}_{\text{finite}}| < \text{min\_B\_for\_alpha}(\alpha)$, `calibrate_threshold` raises `ValueError("insufficient valid nulls")`.
4. Rank index $k$ is calculated strictly over $|\mathcal{M}_{\text{finite}}|$:
   $$k = \lceil (|\mathcal{M}_{\text{finite}}| + 1)(1 - \alpha) \rceil$$
5. Record $n_{\text{no\_eligible}}$, $n_{\text{finite\_maxima}}$, and the abstention fraction in `threshold_uncertainty.csv`, `null_validation.json`, and `table_abstention.csv`.

**Hard Rule:** A detector may never be reported as "robust to missingness" without publishing its power and abstention rate side-by-side (`AGENTS.md` Rule 11).

---

## 4. Nested Rack Nuisance Estimation & Error Covariance Closed Form

### The Identification Trap in Multi-Rack Canary Deployments
In `canary_ssm/factor.py`, the observation model decomposes log latency into baseline host mean $\mu_i$, fleet common factor $f_t$, rack-shared nuisance shift $\gamma_{r(i), t}$, and host error:
$$y_{it} = \mu_i + \lambda_i f_t + \gamma_{r(i), t} + e_{it}$$
For identifiability between the fleet factor and rack nuisance shifts, unexposed baseline controls must satisfy the weighted zero-sum constraint:
$$\sum_{j \in \text{controls}} W_j \hat{\gamma}_{r(j), t} = \sum_{r} W_r \hat{\gamma}_{r, t} = 0, \quad \text{where } W_r = |C_{r, t}|, \quad W_{\text{tot}} = \sum_r W_r$$

Residuals on canaries are formed by subtracting the pre-period mean, estimated fleet factor, and estimated same-rack nuisance:
$$\hat{r}_{it} = y_{it} - \hat{\mu}_i - \hat{\lambda}_i \hat{f}_t - \hat{\gamma}_{r(i), t}$$

### Residual Estimation Error Covariance
Because $\hat{f}_t$ and $\hat{\gamma}_{r, t}$ are estimated from control hosts, their sampling errors introduce contemporaneous covariance across all canaries.

Let:
- $U_t^{\text{fleet}} = \text{Var}(\hat{f}_t - f_t) = \frac{\sigma_{\text{meas}}^2}{\sum_{j \in C_t} \hat{\lambda}_j^2}$
- $U_{r, t}^{\text{rack}} = \text{Var}(\hat{\gamma}_{r, t} - \gamma_{r, t}) = \frac{\sigma_{\text{meas}}^2}{|C_{r, t}|}$
- $\bar{\lambda}_{\text{fleet}} = \frac{1}{W_{\text{tot}}} \sum_{j \in C_t} \hat{\lambda}_j$
- $\bar{\lambda}_r = \frac{1}{|C_{r, t}|} \sum_{j \in C_{r, t}} \hat{\lambda}_j$
- $\Delta \lambda_r = \bar{\lambda}_r - \bar{\lambda}_{\text{fleet}}$

For two canaries $i_1, i_2$ residing on racks $r_1, r_2$:
$$\text{cov\_U}[t, i_1, i_2] = (\lambda_{i_1} \lambda_{i_2} - \Delta \lambda_{r_1} \Delta \lambda_{r_2}) U_t^{\text{fleet}} + \delta_{r_1 r_2} U_{r_1, t}^{\text{rack}} - \frac{\sigma_{\text{meas}}^2}{W_{\text{tot}}}$$

### Defect in Legacy Formula vs. Closed Form
The legacy formula in `canary_ssm/factor.py`:
$$\text{cov\_U}_{\text{legacy}}[t, i_1, i_2] = \delta_{r_1 r_2} U_{r_1, t}^{\text{rack}} + (\lambda_{i_1} \lambda_{i_2} - \bar{\lambda}_C^2) U_t^{\text{fleet}}$$
omitted the $-\sigma_{\text{meas}}^2 / W_{\text{tot}}$ zero-sum coupling and subtracted fleet-level $\bar{\lambda}_C^2$ instead of rack deviations $\Delta \lambda_{r_1} \Delta \lambda_{r_2}$.

**Consequences of the Legacy Formula:**
1. Violated Cauchy-Schwarz bounds between hosts on different racks.
2. Produced indefinite (non-positive-semidefinite) measurement error matrices with negative eigenvalues ($\lambda_{\min} < -0.003$).
3. Triggered fatal LAPACK Cholesky factorization failures in `canary_ssm/detectors.py` (`cho_factor` error: `Internal potrf return info = [3]`).

**Verification of the Closed Form:**
The corrected closed form guarantees positive semi-definiteness ($V \succ 0, \lambda_{\min} \ge +2.5 \times 10^{-5}$) and was independently validated against a 400,000-replication Monte Carlo simulation in `tests/test_rack_covariance_mc.py`. All matrix elements match within 3.5 standard errors of Monte Carlo sampling noise.

---

## 5. Summary Protocol Checklist for New PRs & Experiments

- [ ] Data role separation strictly obeyed (`dev` $\to$ `calibration` $\to$ `null_validation` $\to$ `test`).
- [ ] No detector module imports `Truth`, `metrics`, or reads `*_truth` files.
- [ ] Hierarchical comparisons specify `prior_mode` and `variance_mode` (matched vs. legacy).
- [ ] Grids obey $\le 24$ candidates per family after the long-run SD bound $\sigma / \sqrt{1 - \rho^2} \le \kappa$.
- [ ] Threshold calibration records $n_{\text{no\_eligible}}$ and $n_{\text{finite\_maxima}}$ and enforces $\ge \lceil(1-\alpha)/\alpha\rceil$.
- [ ] Nested rack adjustments use the exact zero-sum covariance closed form.
- [ ] Null validation runs exact Beta-Binomial validity gate (Gate G2).
- [ ] Shared-step failure is acknowledged as an OPEN DEFECT; no claim of universal calibration is made.
