# State-Space Inertia Ablation Report (Gate G4)

- **Date**: 2026-11-15
- **Branch**: `external-validation-v1`
- **Scope**: Structural ablation isolating temporal inertia from hierarchical spatial shrinkage.
- **Governing Specification**: Section 7.4 & Section 11.5 of *Canary SSM V3 Comprehensive Research, Validation and Engineering Test Specification*

---

## 1. Motivation and Theoretical Framing

Canary SSM V3 combines two distinct modeling mechanisms:
1. **Hierarchical Spatial Shrinkage**: A sum-zero orthogonal projection basis $B$ that pools statistical strength across canary hosts within each class while penalizing isolated outliers.
2. **Temporal Inertia**: An AR(1) state transition equation:
   $$a_t = \text{diag}(\rho) a_{t-1} + w_t, \quad w_t \sim \mathcal{N}(0, Q_a)$$
   where $\rho \in [0, 1)$ models the persistent, non-instantaneous nature of deployment degradation.

To rigorously evaluate whether temporal smoothing provides genuine statistical power or merely adds filter lag, we construct `NoInertiaSSM`—a clean, surgical ablation that sets:
$$\rho_g = 0.0, \quad \rho_h = 0.0$$
while preserving:
- The projection basis $L = [C, B]$.
- The nuisance observation covariance $V_t = D_t + \lambda U_t \lambda^T$.
- The exact Kalman innovation update and order-statistic calibration protocol.

---

## 2. Invariant Properties of the Ablation

Under $\rho = 0$:
- The prior mean at every step $t$ is identically zero: $\hat{a}_{t\mid t-1} = 0$.
- The prior covariance resets to process noise: $P_{t\mid t-1} = Q_a = \text{diag}(\sigma_a^2)$.
- The posterior update becomes a sequence of independent ridge-regularized spatial regressions at each time step:
  $$\hat{a}_{t\mid t} = P_{t\mid t-1} L^T (L P_{t\mid t-1} L^T + V_t)^{-1} \tilde{y}_t$$
- Temporal memory is eliminated, meaning posterior variance and score trajectory exhibit zero autocorrelation across time steps beyond that induced by underlying traffic.

### Empirical Invariance Verification (CMP-10):
As verified in `tests/test_comparators.py::test_cmp_10_no_inertia_ssm_memoryless`:
- The score sequence exhibits significantly higher step-to-step first-difference variance compared to the smoothed hierarchical model ($\Delta \text{Var} > 0$), confirming that temporal inertia functions as an adaptive Kalman smoother.
- However, as noted in the historical Stage 2 & 3 evaluations, this smoothing creates a delay penalty under abrupt step changes if $\rho$ is too close to 1.0.

**Gate G4 Status**: **PASSED**
