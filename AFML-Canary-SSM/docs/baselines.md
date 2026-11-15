# Baseline & Comparator Specifications (`WP-E1`, `WP-E2`)

All sequential baselines operate on the **exact same adjusted residual stream** (`Adjusted`), eligibility mask (`adj.elig`), observation mask (`adj.obs`), and pre-period standardisation (`adj.sigma`) as every hierarchical SSM detector.

Contracts enforced across every method in [`canary_ssm/baselines.py`](../canary_ssm/baselines.py) and `canary_ssm/baselines_extra.py`:
1. **No truth leakage:** Never imports `Truth`, `simulate`, or `metrics`.
2. **Causal up to `t`:** Release score `score[t]` depends only on observations `<= t`. Scores for `t < t0` are `NaN`.
3. **Missingness:** An unobserved minute (`~np.isfinite(z[t, i])`) leaves host `i`'s running accumulator unchanged (no zero-imputation). Ineligibility (`~adj.elig[t]`) is enforced downstream identically via `DetectorOutput.elig` in `first_alarm` and `release_max`.
4. **Budget parity (`WP-E3`):** Every comparator family has `<= 24` candidates in `configs/grids_v2.yaml`, tuned by the identical 5-fold cross-validation + 1-SE protocol on the `dev` set and calibrated on the `calibration` plain nulls.

---

## 1. Original Handshake Baselines (`canary_ssm/baselines.py`)

Let $r_{i,t}$ denote the factor- and workload-adjusted residual for canary $i \in \{1,\dots,n_c\}$, and $z_{i,t} = r_{i,t} / \hat{\sigma}_i$ where $\hat{\sigma}_i$ is the pre-period standard deviation.

1. **`matched_contrast(adj, window=1)`**
   Trailing $w$-minute mean across observed canaries minus observed controls at minute $t$ (using raw class-adjusted residuals without cross-class factor weighting: $\bar{y}^{\text{canary}}_{t-w+1:t} - \bar{y}^{\text{control}}_{t-w+1:t}$ over `obs & decision_obs` — actually over finite adjusted residuals / control-matched class offsets as already implemented). Candidates: $w \in \{1, 5, 10, 15, 30\}$ (5 candidates).
2. **`adj_ewma(adj, alpha=0.10)`**
   Per-canary exponentially weighted moving average $Z_{i,t} = \alpha z_{i,t} + (1 - \alpha) Z_{i,t-1}$ for $t \ge t_0$ ($Z_{i,t_0-1}=0$), normalised by asymptotic variance $\sqrt{\alpha / (2 - \alpha)}$; release score $\max_i Z_{i,t} / \sqrt{\alpha / (2 - \alpha)}$. Candidates: $\alpha \in \{0.02, 0.05, 0.10, 0.20, 0.35, 0.50\}$ (6 candidates).
3. **`adj_cusum(adj, k=0.25)`**
   Per-canary one-sided Page CUSUM on $z_{i,t}$:
   $$C_{i,t} = \max\bigl(0,\, C_{i,t-1} + z_{i,t} - k\bigr), \quad C_{i,t_0-1} = 0, \qquad S_t = \max_{1 \le i \le n_c} C_{i,t}.$$
   Candidates: $k \in \{0.10, 0.25, 0.50, 0.75, 1.00, 1.50\}$ (6 candidates).
4. **`topk_cusum(adj, K=3, k=0.25)`**
   Sum of the top-$K$ largest per-host CUSUM statistics $C_{(1),t} \ge \dots \ge C_{(n_c),t}$:
   $$S_t = \sum_{j=1}^{\min(K, n_c)} C_{(j),t}.$$
   Candidates: $K \in \{1, 2, 3, 5, 7, 10\} \times k \in \{0.25, 0.50, 0.75, 1.00\}$ (24 candidates).

---

## 2. Exact AR(1) Prewhitening Used by Sequential Comparators

Under an AR(1) null $z_{i,t} = \phi_i z_{i,t-1} + \eta_{i,t}$ with $\operatorname{Var}(z_{i,t}) = 1$ and $\phi_i = \hat{\phi}_{e, g(i)}$ from the fitted `Nuisance` model (defaulting to $0$ if omitted):
When host $i$'s previous valid observation was at $t_{\text{prev}} = t - \Delta$ ($\Delta \ge 1$; initialized from pre-period when available, else starting cleanly at first observed $t \ge t_0$ with $\Delta \to \infty$, i.e. $\phi_i^\Delta = 0$), the exact unit-variance innovation is:
$$e_{i,t} = \frac{z_{i,t} - \phi_i^{\Delta} z_{i,t_{\text{prev}}}}{\sqrt{1 - \phi_i^{2\Delta}}}.$$
Under $H_0$, $e_{i,t} \stackrel{\text{i.i.d.}}{\sim} \mathcal{N}(0, 1)$ even across arbitrary missing-data gaps $\Delta > 1$. Under a persistent mean shift $\delta$ in $z_{i,t}$, the steady-state innovation mean (for $\Delta = 1$) is:
$$\delta_{\text{pw}} = \frac{(1 - \phi_i)\,\delta}{\sqrt{1 - \phi_i^2}} = \sqrt{\frac{1 - \phi_i}{1 + \phi_i}}\,\delta.$$

---

## 3. Additional Strong Baselines (`WP-E1`, `canary_ssm/baselines_extra.py`)

### 3.1 `wmean` — Windowed Mean (Stateless Persistence Comparator, `WP-B4`)
Per canary $i$ and trailing window $w$ minutes $[ \max(t_0, t - w + 1),\, t ]$, compute the sample mean of finite standardised residuals $\bar{z}_{i, t, w}$ scaled by $\sqrt{m_{i,t,w}}$ where $m_{i,t,w} \ge 1$ is the count of observed minutes in the window (so unit-variance under i.i.d. nulls), or top-$K$ sum across hosts:
$$S_t = \sum_{j=1}^{\min(K, n_c)} \left(\sqrt{m_{(j),t,w}}\,\bar{z}_{(j), t, w}\right)^+, \qquad K \in \{1, 3, 5\},\; w \in \{5, 10, 15, 30, 45\}$$
(15 candidates).

### 3.2 `ar_cusum` — Residual-Chart CUSUM on AR(1)-Prewhitened Residuals
On exact prewhitened unit-variance innovations $e_{i,t}$ with AR parameter $\phi_i$ from nuisance:
since a persistent shift $2k$ in raw $z$-units maps to a reference value $k_{\text{pw}, i} = k \sqrt{(1-\phi_i)/(1+\phi_i)}$ (equivalent to unnormalised $e^{\text{raw}}_t = z_t - \phi z_{t-1}$ with $(1-\phi)k$ divided by $\sqrt{1-\phi^2}$):
$$C^{\text{AR}}_{i,t} = \max\bigl(0,\, C^{\text{AR}}_{i,t-1} + e_{i,t} - k_{\text{pw}, i}\bigr), \qquad S_t = \max_i C^{\text{AR}}_{i,t}.$$
Candidates: $k \in \{0.10, 0.25, 0.50, 0.75\}$ (4 candidates). (In post-rollout testing if `adj_cusum`'s prewhitened relative improves power under strong $\phi_e$, H4 measures that gain cleanly.)

### 3.3 `glr_window` — Sliding-Window One-Sided Normal GLR
**Reference:** Lai (1995), *Sequential Analysis* (windowed CUSUM/GLR); Siegmund & Venkatraman (1995).
First prewhiten $z_{i,t} \mapsto e_{i,t}$ as in Section 2 so $e_{i,t} \sim \mathcal{N}(0, 1)$ under $H_0$. Let $C_{i,t} = \sum_{s=t_0}^{t} e_{i,s}\mathbb{I}\{\text{obs}_{i,s}\}$ and $N_{i,t} = \sum_{s=t_0}^t \mathbb{I}\{\text{obs}_{i,s}\}$. Over candidate changepoints $s \in [\max(t_0, t - W + 1),\, t]$ with $n_{i,s,t} = N_{i,t} - N_{i,s-1} > 0$, define the positive-shift standardised scan statistic:
$$U^+_{i,s,t} = \max\!\left(0,\, \frac{C_{i,t} - C_{i,s-1}}{\sqrt{n_{i,s,t}}}\right), \qquad G_{i,t} = \max_{s} \frac{(U^+_{i,s,t})^2}{2}.$$
Release score is the sum of top-$K$ sorted host values: $S_t = \sum_{j=1}^{\min(K, n_c)} G_{(j), t}$.
Candidates: $W \in \{15, 30, 45, 60\} \times K \in \{1, 3, 5\}$ (12 candidates).

### 3.4 `sparse_mix_glr` — Xie–Siegmund Multi-Stream Mixture GLR
**Reference:** Xie, Y. & Siegmund, D. (2013), *"Sequential multi-sensor change-point detection"*, *The Annals of Statistics*, **41**(2), 670–692 (arXiv:1203.2855). Specifically Equations **(2)**–**(4)** (Section 2, positive-shift multi-sensor mixture procedure $T_2(p_0, b)$).

Given $N = n_c$ parallel prewhitened streams $e_{i,t}$ with cumulative sums over candidate onset $s \in [\max(t_0, t - W + 1),\, t]$ and standardised stream statistic $U_{i,s,t} = (C_{i,t} - C_{i,s-1}) / \sqrt{n_{i,s,t}}$ (0 if $n_{i,s,t}=0$):
for hypothesised sparse affected fraction $p_0 \in (0, 1]$, Eq. (4) of Xie & Siegmund defines the one-sided mixture log-likelihood ratio:
$$M_t(p_0, W) = \max_{\max(t_0, t-W+1) \le s \le t} \sum_{i=1}^{n_c} \log\Bigl(1 - p_0 + p_0 \exp\!\bigl(\tfrac{1}{2}(U^+_{i,s,t})^2\bigr)\Bigr), \qquad U^+_{i,s,t} = \max(U_{i,s,t}, 0),$$
evaluated in log-sum-exp form ($\text{logaddexp}(\log(1-p_0),\, \log p_0 + \frac{1}{2}(U^+_{i,s,t})^2)$) for exact overflow immunity.
Candidates: $p_0 \in \{0.1, 0.3, 0.5\} \times W \in \{30, 60\}$ (6 candidates).
Per-host localisation score at time $t$: each host's mixture summand $\log(1 - p_0 + p_0 \exp(\frac{1}{2}(U^+_{i,s^*,t})^2))$ at the maximizing changepoint $s^*$.

### 3.5 `bocpd` — Adams–MacKay Bayesian Online Changepoint Detection (Directional)
**Reference:** Adams, R. P. & MacKay, D. J. C. (2007), *"Bayesian Online Changepoint Detection"*, arXiv:0710.3742, Section 2, Equations **(1)**–**(3)**, combined with Murphy (2007) Normal–Gamma conjugate observation update for unknown mean $\mu$ and unknown precision $\tau = 1/\sigma^2$.

Using prewhitened unit-variance residuals $e_{i,t}$ run sequentially across the full rollout ($t = 0, \dots, T-1$ so pre-period builds steady-state run lengths $\ge t_0$, or capped at max active run-length horizon):
- Conjugate prior for each newly started run length ($r=0$): $\mu_0 = 0,\; \kappa_0 = 1.0,\; \alpha_0 = 1.0,\; \beta_0 = 1.0$.
- Given active run-length $r$ hyperparameters $(\mu_r, \kappa_r, \alpha_r, \beta_r)$, the Student-$t$ predictive density (Adams & MacKay Sec. 2 / Eq. 1 ingredient) is:
  $$\pi_{r}(e_{i,t}) = t_{\nu_r}\!\left(e_{i,t};\; \mu = \mu_r,\; s^2 = \frac{\beta_r (\kappa_r + 1)}{\alpha_r \kappa_r}\right), \qquad \nu_r = 2\alpha_r.$$
- Constant hazard $H = 1 / \lambda_h$, growth and changepoint probabilities (Eq. 3 message passing):
  $$P(r_t = r_{t-1}+1, x_{1:t}) = P(r_{t-1}, x_{1:t-1})\,\pi_{r_{t-1}}(x_t)\,(1 - H),$$
  $$P(r_t = 0, x_{1:t}) = H \sum_{r_{t-1}} P(r_{t-1}, x_{1:t-1})\,\pi_{r_{t-1}}(x_t).$$
- Conjugate update for surviving run length $r+1$:
  $$\kappa' = \kappa + 1,\quad \mu' = \frac{\kappa\mu + x}{\kappa'},\quad \alpha' = \alpha + \frac{1}{2},\quad \beta' = \beta + \frac{\kappa (x - \mu)^2}{2(\kappa + 1)}.$$
- Unobserved minute (`~isfinite`): prediction & conjugate update are skipped; previous posterior $P(r_t \mid x_{1:t})$ is carried forward unchanged.
- **Directional release score (`WP-E1`):** At $t \ge t_0$, a rollout changepoint occurred at or after $t_0$ iff $r_t < t - t_0 + 1$, and positive mean shift iff post-update $\mu_{t, r} > 0$:
  $$p^{\text{BOCPD}}_{i,t} = \sum_{r=0}^{\min(t - t_0,\, r_{\max})} P(r_t = r \mid x_{1:t})\,\mathbb{I}\{\mu_{t, r} > 0\}, \qquad S_t = \max_{1 \le i \le n_c} p^{\text{BOCPD}}_{i,t}.$$
Candidates: $\lambda_h \in \{60, 120, 240\}$ (3 candidates).

### 3.6 `msprt` — Mixture Sequential Probability Ratio Test ("Peeking-Safe")
**Reference:** Johari, R., Pekelis, L., & Walsh, D. J. (2017/2022), *"Always Valid Inference: Continuous Monitoring of A/B Tests"*, *Operations Research* (arXiv:1512.04922), Section 2.2 (Gaussian normal mixing distribution $\mathcal{N}(0, \tau^2)$).

For prewhitened unit-variance stream $e_{i,t}$ ($\sigma = 1$) starting at $t_0$, let $m_{i,t}$ be the count of observed minutes in $[t_0, t]$ and $S_{i,t} = \sum_{s=t_0}^t e_{i,s}\mathbb{I}\{\text{obs}_{i,s}\}$. With Normal mixing distribution $\mathcal{N}(0, \tau^2)$ on the mean shift under $H_1$:
$$\Lambda_{i,t} = \sqrt{\frac{\sigma^2}{\sigma^2 + m_{i,t}\tau^2}} \exp\!\left(\frac{\tau^2 S_{i,t}^2}{2\sigma^2(\sigma^2 + m_{i,t}\tau^2)}\right),$$
always-valid $p$-value $p_{i,t} = \min_{t_0 \le s \le t} \min(1, 1/\Lambda_{i,s})$, and release score $S_t = \max_i (-\log p_{i,t}) = \max_{i,\, t_0 \le s \le t} \log^+(\Lambda_{i,s})$. Computed directly in log space (`0.5*log(s2/(s2 + m*tau^2)) + tau^2 * S^2 / (2*s2*(s2 + m*tau^2))`) with missing observations leaving $(m_{i,t}, S_{i,t}, p_{i,t})$ unchanged.
Candidates: $\tau \in \{0.25, 0.5, 1.0, 2.0\}$ (4 candidates).

### 3.7 `mw_judge` — Rank-Based Sliding-Window Canary Judge (Kayenta Style)
**Reference:** Netflix / Spinnaker Kayenta (`NetflixACAJudge`) nonparametric Mann–Whitney U comparison between canary and baseline distributions ([Spinnaker Kayenta Canary Judge documentation](https://spinnaker.io/docs/guides/user/canary/judge/canary-judge/)).

Per metric class $g$ represented by canaries and controls, within a trailing causal window $[\max(0, t - w + 1),\, t]$ (taking finite post-factor / control-aligned residuals $r^{\text{adj}}_{i,s}$ of class-$g$ canaries $X_g$ vs finite adjusted class-$g$ control residuals $Y_g$ over the same $w$-minute window; fallback $0$ if sample size $< 3$ per group):
compute the standardized Mann–Whitney $U$ normal-approximation $z$-statistic (including exact tie variance correction, `scipy.stats.mannwhitneyu` equivalent):
$$z_{g,t} = \frac{U_{g,t} - \frac{n_1 n_2}{2}}{\sigma_{U,t}}, \qquad S_t = \max_g z_{g,t}$$
where $U_{g,t}$ counts pairs with canary $>$ control (one-sided directional regression: latency higher in canary than control).
Candidates: $w \in \{15, 30\}$ (2 candidates).
