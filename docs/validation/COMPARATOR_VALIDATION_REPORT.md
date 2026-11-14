# External Comparator Verification Report (Gate G4)

- **Date**: 2026-11-15
- **Branch**: `external-validation-v1`
- **Scope**: Implementation, interface parity, and verification of external deployment analysis benchmarks.
- **Governing Specification**: Section 11 of *Canary SSM V3 Comprehensive Research, Validation and Engineering Test Specification*

---

## 1. Executive Summary

Gate G4 incorporates industry-standard progressive deployment and canary analysis algorithms into the evaluation harness, enabling rigorous, head-to-head empirical benchmarking against Canary SSM V3 under identical experimental conditions and calibrated false-alert budgets.

All comparators were verified via unit tests CMP-01 to CMP-10 (`tests/test_comparators.py`) and adhere strictly to the `DetectorOutput` interface:

| Comparator | Source / Inspiration | Theoretical Mechanism | Test Status |
|---|---|---|---|
| **KayentaJudge** | Netflix / Spinnaker Kayenta | Non-parametric Mann-Whitney U test with directionality, minimum sample gate ($N \ge 5$), and effect size filtering. | **PASSED** (CMP-01..04) |
| **SLOThreshold** | Prometheus / Datadog SLOs | Direct differential contrast ($\bar{z}_{\text{canary}} - \bar{z}_{\text{control}}$) over rolling evaluation window. | **PASSED** (CMP-05..06) |
| **ArgoRolloutsPolicy** | Argo Rollouts (`analysisRun`) | Step-wise metric evaluation with `failureLimit` (AR-1, AR-3, AR-5) and consecutive vs cumulative modes. | **PASSED** (CMP-07..08) |
| **FlaggerPolicy** | Weaveworks Flagger | Step-weight incrementation with cumulative failed-check budget before aborting. | **PASSED** (CMP-09) |
| **NoInertiaSSM** | Mechanistic Ablation | Hierarchical state-space model with temporal persistence neutralized ($\rho = 0.0$). | **PASSED** (CMP-10) |

---

## 2. Benchmark Design Principles

1. **Information Parity**: Every comparator operates on the identical adjusted residuals `adj` and observed presence masks `adj.obs` as the SSM detectors.
2. **Causal Streaming Mode**: In addition to batch classification, all comparators expose a rolling scoring mode $s_t(y_{1:t})$ producing causal time-series scores for sequential stopping time evaluation.
3. **Budget Equivalence**: Decision thresholds for all comparators are calibrated empirically on $B \ge 1,000$ healthy null rollouts to achieve an identical rollout-level false alert budget $\alpha = 0.05$.

**Gate G4 Status**: **PASSED**
