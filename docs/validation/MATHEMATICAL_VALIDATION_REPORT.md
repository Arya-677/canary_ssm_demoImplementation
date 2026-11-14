# Mathematical Validation and Proofs Certification Report (Gate G2)

- **Date**: 2026-11-15
- **Branch**: `external-validation-v1`
- **Scope**: Structural and numerical verification of the state-space model, Kalman update, projection basis, and nuisance factor formulation.
- **Governing Specification**: Section 7 of *Canary SSM V3 Comprehensive Research, Validation and Engineering Test Specification*

---

## 1. Executive Summary

Gate G2 requires independent algebraic and numerical verification of the foundational mathematical primitives in Canary SSM V3. All tests were executed via `tests/test_mathematical_validation.py` and passed with machine-precision accuracy.

| Component | Mathematical Condition | Numerical Benchmark | Verification Result |
|---|---|---|---|
| **Kalman Recursion** | Exact algebraic step solution | Scalar 2-step analytical fixture | **MATCH** ($< 10^{-16}$) |
| **Joseph Covariance** | Positive semi-definiteness & symmetry | Condition numbers $10^2$ to $10^{12}$ | **PASSED** ($\lambda_{\min} \ge 0$) |
| **Basis Orthogonality** | $C^T B = 0$ | Arbitrary class groupings | **PASSED** ($\|C^T B\|_{\infty} < 10^{-12}$) |
| **Basis Orthonormality** | $B^T B = I_{n - G}$ | Block-diagonal null-space basis | **PASSED** ($\|B^T B - I\|_{\infty} < 10^{-12}$) |
| **Sum-Zero Invariance** | $\sum_{i \in \mathcal{G}_g} B_{i, k} = 0$ | Per-class basis vectors | **PASSED** ($< 10^{-12}$) |
| **Inertia Model Construction**| Correct dimension allocation ($L, \rho, \sigma_q$) | Hierarchical, Independent, Pooled | **PASSED** |

---

## 2. Hierarchical Basis Orthogonality Proof and Verification

In Canary SSM V3, multi-host canary effect states are decomposed into:
$$a = C \theta + B b$$
where:
- $C \in \mathbb{R}^{n \times G}$ is the class allocation matrix: $C_{i, g} = 1$ if host $i$ belongs to class $g$, and $0$ otherwise.
- $\theta \in \mathbb{R}^G$ represents the shared class-level effect.
- $B \in \mathbb{R}^{n \times (n - G)}$ represents the orthogonal deviation basis within each class.
- $b \in \mathbb{R}^{n - G}$ represents the host-specific deviation from the class mean.

### Mathematical Invariants:
1. **Separation of Scales**: Deviation effects $b$ must have zero mean across each class. Therefore, for each class $g$ with size $m_g > 1$:
   $$\mathbf{1}_{m_g}^T B_g = \mathbf{0}$$
   which directly guarantees:
   $$C^T B = \mathbf{0}$$
2. **Isotropic Prior**:
   $$B^T B = I_{n - G}$$
   ensuring that independent prior variances on $b$ translate to identical isotropic variance across deviations.
3. **Singleton Invariance**: If a class contains only one host ($m_g = 1$), it cannot deviate from its own mean. Hence, no deviation columns are generated for singletons ($m_g - 1 = 0$).

### Numerical Test Configurations:
The test suite evaluated 5 distinct class configurations:
1. **Balanced Classes**: $[0, 0, 0, 0, 1, 1, 1, 1]$ ($n=8, G=2, \dim(B)=6$).
2. **Unbalanced Classes**: $[0, 0, 0, 0, 1, 1, 2, 2, 2, 2, 2]$ ($n=11, G=3, \dim(B)=8$).
3. **All Singletons**: $[0, 1, 2, 3]$ ($n=4, G=4, \dim(B)=0$).
4. **Mixed Singletons & Groups**: $[0, 0, 0, 1, 2, 3, 3, 3]$ ($n=8, G=4, \dim(B)=4$).
5. **Monolithic Single Class**: $[0, \dots, 0]$ ($n=12, G=1, \dim(B)=11$).

In all cases, $\|C^T B\|_{\infty} < 10^{-12}$ and $\|B^T B - I\|_{\infty} < 10^{-12}$.

---

## 3. Observation Covariance Decomposition

The full observation covariance is given by:
$$V_t = D_t + \lambda U_t \lambda^T$$
where:
- $D_t = \text{diag}(v_{g(i)}^2)$ represents independent per-host measurement variances.
- $\lambda \in \mathbb{R}^n$ is the pre-period estimated factor loading vector.
- $U_t \in \mathbb{R}$ is the variance of the rank-1 common factor estimate $\hat{f}_t$.

Because $D_t \succ 0$ and $U_t \ge 0$, the Woodbury matrix identity or direct Sherman-Morrison rank-1 update applies, ensuring $V_t$ is strictly positive definite and invertible at every time step $t$.

**Gate G2 Status**: **PASSED**
