# Telemetry Schema and Causal Availability Report (Gate G3)

- **Date**: 2026-11-15
- **Branch**: `external-validation-v1`
- **Scope**: Telemetry schema validation, stream ordering, late arrivals, missingness masking, and strict online causality proofs.
- **Governing Specification**: Section 5 of *Canary SSM V3 Comprehensive Research, Validation and Engineering Test Specification*

---

## 1. Executive Summary

Gate G3 certifies the data integrity and causal availability properties of the Canary SSM V3 ingestion and evaluation pipeline. All ten required validation tests (TEL-01 to TEL-10) were executed and passed via `tests/test_telemetry_integrity.py`.

| Test ID | Requirement / Invariant | Validation Mechanism | Result |
|---|---|---|---|
| **TEL-01** | Duplicate Key Handling | Unique `(host_id, timestamp)` constraint enforcement | **PASSED** |
| **TEL-02** | Late Arrival Invariance | Streaming masking; delayed records do not mutate past decisions | **PASSED** |
| **TEL-03** | Out-of-Order Stream Shuffling | Temporal sorting parity | **PASSED** |
| **TEL-04** | Missing Observation Masking | Kalman sub-matrix projection on observed coordinates | **PASSED** |
| **TEL-05** | Timestamp Monotonicity | Non-decreasing sequence verification ($\Delta t \ge 0$) | **PASSED** |
| **TEL-06** | Invalid Metric Rejection | Rejection of non-positive, NaN, and infinite raw latencies | **PASSED** |
| **TEL-07** | Host Identity Lifecycle | Partitioning and dimensional consistency across canary/control | **PASSED** |
| **TEL-08** | Exposure Leakage Prevention | Strict disjointness between canary and control populations | **PASSED** |
| **TEL-09** | Pre-Period Immutability | Nuisance parameters $\hat{\mu}_i, \hat{\beta}_i, \hat{\lambda}_i$ invariant to post-period shocks | **PASSED** |
| **TEL-10** | Strict Causal Invariance | Prefix property: decision score at $t$ is invariant to $t' > t$ | **PASSED** |

---

## 2. Mathematical Definition of Causal Invariance (TEL-10)

Let $y_{1:T} = [y_1, y_2, \dots, y_T]$ denote the full sequence of observations up to horizon $T$, and let $s_t(y_{1:t})$ denote the detector score computed at time $t$ using only historical observations up to $t$.

A detector satisfies strict online causality if and only if:
$$\forall t \le T, \quad s_t(y_{1:T}) = s_t(y_{1:t})$$

Furthermore, under any arbitrary future perturbation $\delta_{t+1:T}$ applied after time $t$:
$$s_t(y_{1:t}, y_{t+1:T} + \delta_{t+1:T}) = s_t(y_{1:t})$$

### Empirical Proof:
In `tests/test_telemetry_integrity.py::test_tel_10_strict_causality_prefix_invariance`, the evaluation was executed on a truncated stream at $t = t_0 + 12$ and compared directly against the full stream evaluated to $T = t_0 + 60$. The resulting score trajectory over $t \in [0, t_0 + 12]$ matched with exact floating-point tolerance ($\|s_{\text{full}} - s_{\text{trunc}}\|_{\infty} < 10^{-12}$).

---

## 3. Late Arrival Invariance (TEL-02)

In production telemetry systems, network partitions or agent buffering may cause observations to arrive out-of-order. Canary SSM V3 maintains two distinct observation masks:
- `observed`: event-time presence (for retrospective offline audits).
- `decision_obs`: arrival-time presence (what the online streaming decision engine was allowed to see at timestamp $t$).

Test TEL-02 verified that when an event timestamped at $t_{\text{delayed}}$ is received after $t_{\text{eval}}$, decisions evaluated at $t < t_{\text{delayed}}$ remain bit-identical.

**Gate G3 Status**: **PASSED**
