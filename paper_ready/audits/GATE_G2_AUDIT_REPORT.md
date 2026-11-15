# Gate G2 Calibration and Exact Beta-Binomial Validity Audit Report

- **Date**: 2026-11-15
- **Branch**: `external-validation-v1`
- **Calibration Sample**: $B = 1,000$ independent healthy null rollouts per method
- **Validation Sample**: $N_{\text{val}} = 500$ independent healthy null rollouts per method
- **Target False Alert Budget**: $\alpha = 0.05$
- **Governing Specification**: Section 13 & Gate G2 of *Canary SSM V3 Comprehensive Research, Validation and Engineering Test Specification*
- **Source Artifacts**: `external_validation_v1/artifacts/calibrated_thresholds.json`, `external_validation_v1/results/gate_g2_audit.csv`

---

## 1. Executive Summary

Gate G2 enforces the core scientific validity criterion: no detector may be evaluated for power or detection delay unless its decision threshold is strictly calibrated and audited to bound the rollout-level false-alert rate at or below $\alpha = 0.05$.

All 9 candidate methods achieved exact statistical validity on $N_{\text{val}} = 500$ unseen validation null rollouts:
- **Maximum Observed FAR**: $0.052 \le 0.075$ (Required bound satisfied).
- **Minimum Binomial P-Value**: $0.4471 \ge 0.01$ (Required significance satisfied).
- **Gate G2 Pass Rate**: **9 / 9 Methods (100.0%)**.

---

## 2. Calibrated Thresholds and Validation Audit Matrix

| Candidate Method | Calibrated Threshold ($\tau$) | Validation $N$ | Observed Alarms ($K$) | Achieved FAR | Exact Binomial $p$-value | Gate G2 Status |
|---|---|---|---|---|---|---|
| **`hier_ssm`** | $-0.03026$ | $500$ | $24$ | **$0.0480$** ($4.8\%$) | $0.6101$ | **PASSED** |
| **`indep_ssm`** | $-0.04739$ | $500$ | $26$ | **$0.0520$** ($5.2\%$) | $0.4471$ | **PASSED** |
| **`no_inertia_ssm`** | $-3.19756$ | $500$ | $21$ | **$0.0420$** ($4.2\%$) | $0.8211$ | **PASSED** |
| **`kayenta_judge`** | $+5.94009$ | $500$ | $23$ | **$0.0460$** ($4.6\%$) | $0.6879$ | **PASSED** |
| **`argo_policy` (AR-3)** | $+16.33333$ | $500$ | $22$ | **$0.0440$** ($4.4\%$) | $0.7591$ | **PASSED** |
| **`flagger_policy`** | $+9.80000$ | $500$ | $22$ | **$0.0440$** ($4.4\%$) | $0.7591$ | **PASSED** |
| **`slo_threshold`** | $+1.72214$ | $500$ | $16$ | **$0.0320$** ($3.2\%$) | $0.9801$ | **PASSED** |
| **`adj_cusum`** | $+65.66507$ | $500$ | $20$ | **$0.0400$** ($4.0\%$) | $0.8728$ | **PASSED** |
| **`glr_window`** | $+49.78621$ | $500$ | $18$ | **$0.0360$** ($3.6\%$) | $0.9441$ | **PASSED** |

---

## 3. Mathematical Basis of the Gate G2 Test

Let $K \sim \text{Binomial}(N_{\text{val}}, p)$ denote the number of false alarms observed on $N_{\text{val}}$ null deployment rollouts under fixed threshold $\tau$. The exact one-sided p-value testing $H_0: p \le \alpha$ against $H_1: p > \alpha$ is:
$$p_{\text{exact}} = \sum_{j=K}^{N_{\text{val}}} \binom{N_{\text{val}}}{j} \alpha^j (1 - \alpha)^{N_{\text{val}} - j}$$

- If $p_{\text{exact}} < 0.01$, the null hypothesis of valid false alarm calibration is rejected at the 1% significance level (threshold is under-conservative / invalid).
- If achieved $\text{FAR} = K / N_{\text{val}} > 0.075$, the detector exceeds the operational margin of error.

Because all 9 methods achieved $p \in [0.447, 0.980]$ and $\text{FAR} \in [0.032, 0.052]$, all methods are confirmed to operate under an identical, empirically verified false-alarm budget.

**Gate G2 Audit Status**: **ALL 9 METHODS VALIDATED (100% PASS)**
