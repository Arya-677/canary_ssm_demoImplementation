# Real-World Kubernetes Testbed Readiness Guide

- **Specification Source**: Section 17 of *Canary SSM V3 Comprehensive Research, Validation and Engineering Test Specification*
- **Target Deployment Environments**: Kubernetes v1.28+, Argo Rollouts v1.6+, Flagger v1.34+, Prometheus / OpenTelemetry
- **Status**: Production Deployment Architectural Specification

---

## 1. System Architecture Overview

Canary SSM V3 is designed to deploy as a sidecar controller or standalone evaluation service operating alongside standard Kubernetes progressive delivery operators:

```
+-------------------------------------------------------------------------------+
|                             Kubernetes Cluster                                |
|                                                                               |
|  +---------------------------+             +-------------------------------+  |
|  |     Application Pods      |             |     Progressive Delivery      |  |
|  |  +---------------------+  |             |  +-------------------------+  |  |
|  |  | Canary Replicas (nc)|  |             |  |   Argo Rollouts /       |  |  |
|  |  +---------------------+  |             |  |   Flagger Controller    |  |  |
|  |  | Control Baseline(N) |  |             |  +------------+------------+  |  |
|  |  +----------+----------+  |             |               ^               |  |
|  +-------------|-------------+             +---------------|---------------+  |
|                | Scrapes / Traces                          | Webhook / Metric |
|                v                                           v                  |
|  +---------------------------+             +-------------------------------+  |
|  | Prometheus / OpenTelemetry|             |    Canary SSM Decision Engine |  |
|  |      Metrics Endpoint     +------------>|  - Pre-period Baseline Fit    |  |
|  +---------------------------+ Query API   |  - Causal Kalman Filter       |  |
|                                            |  - Calibrated Risk Decision   |  |
|                                            +-------------------------------+  |
+-------------------------------------------------------------------------------+
```

---

## 2. Ingestion Adapter and Pre-Rollout Phase

### 2.1 Telemetry Contract
The ingestion adapter queries the cluster monitoring plane (Prometheus PromQL or OpenTelemetry Collector) at regular scrape intervals (e.g., $\Delta t = 15$ seconds or $60$ seconds):
- Metric 1: Request Latency ($p_{50}, p_{90}, p_{99}$ or mean log latency $y_{it}$ per pod).
- Metric 2: Request Rate / Concurrency ($x_t = \log \text{QPS}$, cluster-wide workload covariate).
- Metric 3: Pod Identity and Metadata (`pod_name`, `deployment_hash`, `node_zone`, `image_tag`).

### 2.2 Pre-Period Baseline Fitting Protocol
1. **Window Duration**: Minimum $T_{\text{pre}} = 30$ to $60$ minutes of stable traffic prior to traffic shifting.
2. **OLS Host Slopes**: Estimate host-specific baseline latency $\hat{\mu}_i$ and workload slope $\hat{\beta}_i$ via:
   $$\hat{\mu}_i, \hat{\beta}_i = \arg\min_{\mu, \beta} \sum_{t=1}^{T_{\text{pre}}} \left( y_{it} - \mu - \beta (x_t - \bar{x}) \right)^2$$
3. **Rank-1 Control Factor Loading**: From unexposed control pods, compute empirical residual factor $\hat{f}_t$ and project onto canary hosts to obtain $\hat{\lambda}_i$.
4. **Parameter Freeze**: All estimated coefficients $(\hat{\mu}, \hat{\beta}, \hat{\lambda}, \hat{\phi}_e, \hat{q}_e)$ are locked and serialized prior to routing canary traffic.

---

## 3. Progressive Delivery Controller Integration

### 3.1 Argo Rollouts Integration via AnalysisTemplate
Canary SSM exposes an HTTP evaluation endpoint (`/v1/rollout/evaluate`) conforming to Argo Rollouts Webhook provider:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: canary-ssm-analysis
spec:
  metrics:
  - name: ssm-canary-risk
    interval: 30s
    successCondition: result.decision == "PASS" || result.decision == "PAUSE"
    failureLimit: 3
    provider:
      web:
        url: "http://canary-ssm-service.monitoring.svc:8080/v1/rollout/evaluate"
        jsonBody:
          rollout_id: "{{args.rollout-id}}"
          canary_service: "{{args.canary-service}}"
          baseline_service: "{{args.baseline-service}}"
          step: "{{args.step-index}}"
        jsonPath: "{$.decision}"
```

### 3.2 Flagger Webhook Integration
```yaml
apiVersion: flagger.app/v1beta1
kind: Canary
metadata:
  name: frontend
spec:
  analysis:
    interval: 1m
    threshold: 5
    maxWeight: 50
    stepWeight: 10
    webhooks:
      - name: "canary-ssm-gate"
        type: rollout
        url: "http://canary-ssm-service.monitoring.svc:8080/v1/flagger/check"
        timeout: 10s
        metadata:
          riskThreshold: "0.05"
```

---

## 4. Operational Edge Cases and Failure Recovery

| Edge Case / Failure Mode | Root Cause in Real Clusters | Mitigation / Safety Protocol |
|---|---|---|
| **Pod Crash / OOMKilled** | Application bug or memory leak | OOM pod is marked `unobserved` ($y_{it} = \text{NaN}$). Kalman sub-projection updates remaining pods without state corruption. If $> 50\%$ canary pods die, trigger immediate `ABORT`. |
| **HPA Autoscaling Churn** | Horizontal Pod Autoscaler spawns new pods mid-rollout | Newly spawned control pods initialize with class fallback loadings until local observations accumulate. Newly spawned canary pods join with prior mean zero. |
| **Node Zone Evacuation** | Kubernetes node drained or cordon event | Pod departure handled via dynamic identity mask. Spatial projection basis $B$ recalculates dimensions dynamically ($n \to n - 1$) preserving orthogonality. |
| **Prometheus Scrape Interruption**| Network partition or Prometheus reload | If zero metrics arrive at step $t$, filter executes time-update only (predict step: $\hat{a}_{t\mid t-1} = F \hat{a}_{t-1}, P_{t\mid t-1} = F P F^T + Q$) and returns state `PAUSE`. |
| **Zero Traffic (Nightly Idle)** | Off-peak traffic drops to $< 1 \text{ QPS}$ | Minimum observation count gate enforces `ABSTAIN` / `PAUSE` if total request count across canary pods is below $N_{\min} = 50$ requests per minute. |

---

## 5. Performance and Resource Footprint

- **Per-step compute latency**: $< 2.5\text{ ms}$ for $N=100$ pods; $< 15\text{ ms}$ for $N=500$ pods.
- **Memory footprint**: $< 64\text{ MB}$ RSS memory per active rollout.
- **External Dependencies**: Zero runtime cloud API dependencies; purely local matrix linear algebra (NumPy / SciPy).
