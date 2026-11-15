# Virtual Data Center & Canary SSM: Honest Technical Limitations & Failure Modes

**Document Version:** 1.0.0  
**Governing Standard:** Antigravity Epistemic Honesty, Causal Parity, and Statistical Safety  
**Repository:** `canary_ssm`

---

## 1. Executive Summary

This document details the known statistical, physical, and computational limitations of the Virtual Data Center simulation engine, the Hierarchical State-Space Model (`OnlineHierarchicalSSM`), and the Multi-Channel Decision Policy (`POLICY-SIDAK-0.05`). 

In accordance with the repository's core guidelines:
> _"A statistical model is exact only conditional on fixed parameters; do not claim causal attribution, sparse Bayesian inference, or novelty. Retain negative results and document honest limitations."_

---

## 2. Statistical & Modeling Limitations

### 2.1 Pre-Period Stationarity & Counterfactual Drift
* **Mechanism:** The time-slicing engine estimates host-level baseline parameters (workload intercept $\mu_i$, workload elasticity $\beta_i$, and common fleet factor loading $\lambda_i$) strictly from pre-exposure records ($t < t_0$).
* **Limitation:** The counterfactual residual $r_{it} = y_{it} - (\hat{\mu}_i + \hat{\beta}_i (x_t - \bar{x}) + \hat{\lambda}_i \hat{f}_t + \hat{\gamma}_j)$ relies on the assumption that pre-period parameters remain invariant during rollout.
* **Failure Mode:** If the datacenter experiences unmodeled macro shifts (e.g. cold-cache post-restart warming, sudden schema migrations, or multi-day non-linear diurnal shifts), the pre-period estimates become biased, inflating residual variance $\sigma_e^2$ and degrading detector power.

### 2.2 Mandatory Concurrent Same-Rack Control Requirement (Identifiability Boundary)
* **Mechanism:** Physical rack nuisances $\gamma_j(t)$ are estimated directly from unexposed baseline controls colocated in the same physical rack $j$.
* **Limitation:** If an allocation deploys canaries across all servers in a given rack ($|C_j| = 0$), rack network degradation and release regression become collinear and mathematically unidentifiable.
* **Detector Behavior:** Rather than guessing or attributing fault to the release, the detector service enforces an identifiability guard, setting `is_unidentifiable = True` and outputting `INSUFFICIENT DATA / CONFLICT`.

### 2.3 Host-Level Risk Cutoffs vs. Fleet-Wide False-Alarm Control
* **Mechanism:** The hierarchical model outputs individual host posterior exceedance probabilities $\Pr(a_{it} > \log(1.02))$.
* **Limitation:** Applying a naive cutoff directly to host posterior risk (e.g. $\Pr > 0.50$) completely fails fleet-wide false-alarm control.
* **Empirical Evidence:** As demonstrated in [results/table_null_validation.csv](file:///results/table_null_validation.csv) and `test_host_risk_cutoff_fails_fleet_control`, an uncalibrated 0.50 host cutoff produces **13.0%** false alerts across 4 hosts over 45 ticks, and lower cutoffs (0.20–0.30) inflate false alerts to **70%–99%**. Calibrating release-level maxima using declared order statistics ($k = \lceil (B+1)(1-\alpha) \rceil$) is mathematically mandatory.

### 2.4 Decoupled Multi-Channel Modeling (Absence of Cross-Metric Dynamic Covariance)
* **Mechanism:** Latency and memory are modeled via two independent sequential state-space filters:
  - Latency: Hierarchical state-space model with Helmert orthonormal contrast basis.
  - Memory: Causal differencing MA(1) Kalman filter with persistence gating.
* **Limitation:** There is no cross-metric Kalman state vector $s_t = [a_{\text{lat}}, g_{\text{mem}}]^T$ with dynamic cross-covariance $\text{Cov}(a_{\text{lat}}, g_{\text{mem}})$.
* **Impact:** While decoupling prevents nuisance leakage between channels, it cannot exploit lead-lag predictive relationships (e.g., early memory accumulation predicting eventual GC thrashing latency spikes before the leak boundary is crossed).

---

## 3. Operational & Telemetry Boundaries

### 3.1 Persistence Horizon Delay Trade-Off
* **Mechanism:** To distinguish genuine persistent leaks from benign garbage collection sawtooth cycles and allocator post-boot warmup ramps, the memory channel enforces a persistence window $H = 15$ ticks above the growth boundary $\kappa_M = 0.50$ MB/min.
* **Limitation:** A genuine memory leak cannot be declared within the first 14 minutes of deployment.
* **Safety Mitigations:** Rapid catastrophic memory exhaustion is guarded by physical capacity thresholds (Headroom $\le 1024$ MB or Time-To-Exhaustion $\le 30$ min triggers immediate `CRITICAL_OOM_RISK`), but statistical trend detection inherently incurs a 15-minute persistence delay.

### 3.2 Low-Volume Observation Noise Uncertainty
* **Mechanism:** Individual request arrivals follow discrete Poisson/normal queuing models.
* **Limitation:** When request volume drops below $\approx 10$ req/tick (e.g. low-traffic microservices or off-peak hours), queuing latency variance $\text{Var}(y_{it})$ expands significantly.
* **Detector Behavior:** Credible intervals widen automatically, reducing test power and increasing detection delay until sufficient traffic accumulates.

### 3.3 Pure CPU Saturation Without Downstream Latency Degradation
* **Mechanism:** In scenario `cpu_regression`, canary instances experience $+0.40$ CPU saturation due to compute-intensive loops.
* **Limitation:** If CPU saturation does not induce server thrashing or queuing delays (latency remaining within $+2\%$ bounds) and memory remains constant, neither the latency SSM nor the memory growth detector will trigger.
* **Retained Negative Result:** The scenario is classified as a `miss` by the latency/memory detector suite. Detecting pure compute saturation requires an explicit CPU utilization metric channel.

---

## 4. Virtual Simulation vs. Real Datacenter Physics

| Physical Property | Virtual Data Center Implementation | Real Production Datacenter Reality |
|---|---|---|
| **Time Granularity** | Discrete 1-minute ticks | Continuous microsecond packet bursts, sub-second GC pauses |
| **Response Functions** | Log-linear queueing & resource approximations | Non-linear lock contention, kernel context switching, memory fragmentation |
| **Network Fabric** | Additive rack nuisance $\gamma_j(t)$ | Top-of-rack buffer drops, ECMP hash polarization, BGP route flapping |
| **Process State** | Continuous numerical MB and CPU utilization | Heap generation arenas, kernel slab allocations, copy-on-write page faults |
| **Clock Synchronization** | Perfect global simulation tick $t$ | PTP/NTP clock drift, leap seconds, distributed timestamp skews |

---

## 5. Summary of Preserved Benchmark Configurations

To preserve comparison integrity across all experimental studies:
1. **Full Benchmark Configs:** `configs/smoke.yaml`, `configs/plain_main.yaml`, `configs/audit.yaml`, `configs/stress.yaml`, and `configs/grids_v2.yaml` remain completely unmodified.
2. **Scenario Demo Configs:** Stored separately in `configs/scenarios/` (`clean_release.json`, `release_leak_two_canaries.json`, etc.) with disjoint parameter namespaces.
3. **Reproducibility Guarantee:** Running `python scripts/demo.py --replay results/scenarios/<scenario>` guarantees exact bit-for-bit reproduction of recorded telemetry and detector outputs.
