# Mathematical Formulation: Canary SSM V3
## Hierarchical, Inertia-Constrained State-Space Models for Safer Software Rollout Decisions

- **Model Classification:** Linear-Gaussian State-Space Model / Dynamic Linear Model (DLM) with Order-Statistic Calibration
- **Mathematical Framework:** Kalman Filtering, Factor Analysis, and Sequential Non-Parametric Calibration

---

### 1. Telemetry Observation & Workload Adjustment

Let $y_{it}$ denote the observed metric (e.g., request latency in milliseconds) for host $i \in \{1, \dots, N\}$ at discrete time $t \in \{1, \dots, T\}$. Telemetry is transformed to the logarithmic scale:
$$z_{it} = \log y_{it}$$

#### 1.1 Pre-Period Nuisance Model
During the pre-rollout window ($t \in \{1, \dots, t_{\text{rollout}}\}$), observed log-latency is modeled as:
$$z_{it} = \mu_i + \beta_i w_t + \boldsymbol{\lambda}_i^T \mathbf{f}_t + \epsilon_{it}, \quad \epsilon_{it} \sim \mathcal{N}(0, \sigma_i^2)$$
where:
- $\mu_i \in \mathbb{R}$ is the host-specific baseline latency offset.
- $w_t \in \mathbb{R}$ is the observed cluster-wide workload stream (e.g., query volume).
- $\beta_i \in \mathbb{R}$ is the host sensitivity to workload fluctuations.
- $\mathbf{f}_t \in \mathbb{R}^r$ is an unobserved $r$-dimensional environmental factor vector capturing shared diurnal shifts.
- $\boldsymbol{\lambda}_i \in \mathbb{R}^r$ is the factor loading vector for host $i$.

#### 1.2 Online Workload Residualization
During the post-rollout monitoring window ($t > t_{\text{rollout}}$), observations are residualized against the frozen pre-period estimates:
$$\tilde{z}_{it} = z_{it} - \hat{\mu}_i - \hat{\beta}_i w_t$$
For control hosts ($i \in \mathcal{C}_{\text{ctrl}}$), the contemporaneous baseline is formed by extracting the leading shared factor component $\hat{\mathbf{f}}_t$ via principal component analysis (PCA) on control residuals:
$$\hat{\mathbf{f}}_t = \left(\hat{\boldsymbol{\Lambda}}_{\text{ctrl}}^T \hat{\boldsymbol{\Lambda}}_{\text{ctrl}}\right)^{-1} \hat{\boldsymbol{\Lambda}}_{\text{ctrl}}^T \tilde{\mathbf{z}}_{\text{ctrl}, t}$$
The adjusted contrast for canary host $i \in \mathcal{C}_{\text{canary}}$ is defined as:
$$e_{it} = \tilde{z}_{it} - \hat{\boldsymbol{\lambda}}_i^T \hat{\mathbf{f}}_t$$

---

### 2. Hierarchical State-Space Formulation

The adjusted contrast vector $\mathbf{e}_t = [e_{1t}, \dots, e_{N_c t}]^T$ contains the combined effect of the software rollout and residual host-level noise.

#### 2.1 State Vector Decomposition
To separate fleet-wide degradation from class-specific hardware responses, the latent state vector $\mathbf{x}_t \in \mathbb{R}^{1 + (K-1)}$ is structured as:
$$\mathbf{x}_t = \begin{bmatrix} a_t \\ \boldsymbol{\delta}_t \end{bmatrix}$$
- **$a_t \in \mathbb{R}$ (Fleet Rollout Effect):** The primary latent health effect shared across all canary hosts.
- **$\boldsymbol{\delta}_t \in \mathbb{R}^{K-1}$ (Class Deviations):** Localized deviations for host classes $k \in \{1, \dots, K\}$. Identifiability is guaranteed by the orthonormal sum-to-zero constraint:
$$\sum_{k=1}^K \delta_{kt} = 0 \implies \delta_{Kt} = -\sum_{k=1}^{K-1} \delta_{kt}$$

#### 2.2 Latent State Transition Equation
The latent state evolves according to a first-order Markov autoregressive process:
$$\mathbf{x}_{t} = \mathbf{F} \mathbf{x}_{t-1} + \mathbf{q}_t, \quad \mathbf{q}_t \sim \mathcal{N}(\mathbf{0}, \mathbf{Q})$$
where the transition matrix $\mathbf{F}$ and process noise covariance $\mathbf{Q}$ are block-diagonal:
$$\mathbf{F} = \begin{bmatrix} \phi_a & \mathbf{0} \\ \mathbf{0} & \phi_\delta \mathbf{I}_{K-1} \end{bmatrix}, \quad \mathbf{Q} = \begin{bmatrix} \sigma_{q,a}^2 & \mathbf{0} \\ \mathbf{0} & \sigma_{q,\delta}^2 \mathbf{I}_{K-1} \end{bmatrix}$$
- $\phi_a \in [0, 1)$ governs temporal persistence / inertia of the fleet effect.
- $\sigma_{q,a}^2$ represents process variance (unmodeled software volatility).

#### 2.3 Observation Equation
The adjusted contrast observations map onto the latent state via observation matrix $\mathbf{H}_t$:
$$\mathbf{e}_t = \mathbf{H}_t \mathbf{x}_t + \mathbf{v}_t, \quad \mathbf{v}_t \sim \mathcal{N}(\mathbf{0}, \mathbf{R}_t)$$
where row $i$ of $\mathbf{H}_t$ (corresponding to canary host $i$ belonging to class $k(i)$) is given by:
$$\mathbf{H}_{i, \cdot} = \begin{bmatrix} 1 & \mathbf{u}_{k(i)}^T \end{bmatrix}$$
with $\mathbf{u}_k$ denoting the $k$-th basis vector of the $(K-1)$-dimensional sum-to-zero contrast matrix.

#### 2.4 Observation Covariance Construction
The observation covariance $\mathbf{R}_t \in \mathbb{R}^{N_c \times N_c}$ is constructed from pre-period residual variances:
$$\mathbf{R}_t = \text{diag}(\hat{\sigma}_1^2, \dots, \hat{\sigma}_{N_c}^2) + \rho \mathbf{I}_{N_c}$$
where $\rho > 0$ provides numerical regularization against ill-conditioned matrix inversions.

---

### 3. Recursive Kalman Filtering & State Estimation

At each time step $t$, state estimation proceeds via classical Kalman filter recursions.

#### 3.1 Prediction Step
$$\hat{\mathbf{x}}_{t|t-1} = \mathbf{F} \hat{\mathbf{x}}_{t-1|t-1}$$
$$\mathbf{P}_{t|t-1} = \mathbf{F} \mathbf{P}_{t-1|t-1} \mathbf{F}^T + \mathbf{Q}$$

#### 3.2 Update Step (Stabilized Joseph Form)
Given observation innovation $\mathbf{v}_t = \mathbf{e}_t - \mathbf{H}_t \hat{\mathbf{x}}_{t|t-1}$ and innovation covariance $\mathbf{S}_t = \mathbf{H}_t \mathbf{P}_{t|t-1} \mathbf{H}_t^T + \mathbf{R}_t$:
$$\mathbf{K}_t = \mathbf{P}_{t|t-1} \mathbf{H}_t^T \mathbf{S}_t^{-1}$$
$$\hat{\mathbf{x}}_{t|t} = \hat{\mathbf{x}}_{t|t-1} + \mathbf{K}_t \mathbf{v}_t$$
$$\mathbf{P}_{t|t} = (\mathbf{I} - \mathbf{K}_t \mathbf{H}_t) \mathbf{P}_{t|t-1} (\mathbf{I} - \mathbf{K}_t \mathbf{H}_t)^T + \mathbf{K}_t \mathbf{R}_t \mathbf{K}_t^T$$
The Joseph formulation is strictly enforced to ensure numerical symmetry and positive semi-definiteness.

#### 3.3 Handling Missing Telemetry
If host $i$ reports missing telemetry at time $t$, row $i$ is pruned from $\mathbf{H}_t$ and $\mathbf{R}_t$. If all hosts miss data, $\mathbf{K}_t = \mathbf{0}$, $\hat{\mathbf{x}}_{t|t} = \hat{\mathbf{x}}_{t|t-1}$, and $\mathbf{P}_{t|t} = \mathbf{P}_{t|t-1}$.

---

### 4. Posterior Harm Probability & Persistence Scoring

#### 4.1 Instantaneous Posterior Harm Probability
The marginal posterior distribution of the fleet effect is Gaussian:
$$a_t \mid \mathbf{e}_{1:t} \sim \mathcal{N}\left(\hat{a}_{t|t}, \sigma_{a,t}^2\right), \quad \sigma_{a,t}^2 = [\mathbf{P}_{t|t}]_{1,1}$$
The instantaneous probability that the canary degradation exceeds the preregistered harm boundary $a^* = \log(1.03) \approx 0.02956$ (a 3.0% latency degradation) is:
$$p_t = P(a_t \ge a^* \mid \mathbf{e}_{1:t}) = 1 - \Phi\left(\frac{a^* - \hat{a}_{t|t}}{\sigma_{a,t}}\right) = \Phi\left(\frac{\hat{a}_{t|t} - a^*}{\sigma_{a,t}}\right)$$
where $\Phi(\cdot)$ denotes the standard normal cumulative distribution function.

#### 4.2 Latent Persistence Score
To filter transient single-observation anomalies, the persistence score at confirmation depth $m \ge 1$ computes the running minimum posterior probability:
$$S_t^{(m)} = \min_{j \in \{0, \dots, m-1\}} p_{t-j}$$
For $m=1$, $S_t^{(1)} = p_t$ (memoryless posterior). For $m > 1$, $S_t^{(m)}$ requires sustained evidence over $m$ consecutive minutes before crossing thresholds.

---

### 5. Order-Statistic Threshold Calibration (Gate G2)

Thresholds are not set arbitrarily. Under the governing Gate G2 protocol:
1. **Null Replay Distribution:** $B = 2,000$ exchangeable null rollouts are passed through the pipeline to obtain maximum per-rollout persistence scores:
   $$M_b = \max_{t \in \{t_{\text{rollout}}+1, \dots, T\}} S_t^{(m)}, \quad b \in \{1, \dots, B\}$$
2. **Order-Statistic Selection:** To calibrate to an exact false-alert budget $\alpha = 0.05$, the threshold $\tau_{\text{high}}$ is selected as the $k$-th order statistic:
   $$k = \lceil (1 - \alpha)(B + 1) \rceil = \lceil 0.95 \times 2001 \rceil = 1,901$$
   $$\tau_{\text{high}} = M_{(1,901)}$$
3. **Exact Finite-Sample Property:** By exchangeability of order statistics, the probability that an independent validation rollout exceeds $\tau_{\text{high}}$ follows an exact Beta distribution:
   $$\text{FAR} \sim \text{Beta}(B + 1 - k + 1, k) = \text{Beta}(101, 1901)$$
   with expected value $\mathbb{E}[\text{FAR}] = \frac{101}{2002} \approx 0.05045$.
4. **Gate G2 Validity Criterion:** On $n = 2,000$ independent validation nulls, the two-sided Beta-Binomial $p$-value must satisfy:
   $$p_{\text{BetaBinom}} \ge 0.01 \quad \text{and} \quad \widehat{\text{FAR}} \le 0.075$$

---

### 6. Reversible Automated Decision Policy

The rollout decision operates as an advisory discrete state machine:
- **State Space:** $\mathcal{S} = \{\text{HEALTHY}, \text{ALARM}, \text{RECOVERED}\}$
- **Alarm Transition:** Triggered at time $t$ if $S_t^{(m)} \ge \tau_{\text{high}}$ for $k$ consecutive steps.
- **Recovery / Resumption Transition:** Following an alarm, if the canary build is rolled back or remediated such that $S_t^{(m)} \le \tau_{\text{low}}$ for $n_{\text{clear}} = 5$ consecutive steps, the policy transitions to $\text{RECOVERED}$.
- **Hysteresis Bands:** $\tau_{\text{high}} \approx 0.85$ (alarm), $\tau_{\text{low}} \approx 0.25$ (recovery).
