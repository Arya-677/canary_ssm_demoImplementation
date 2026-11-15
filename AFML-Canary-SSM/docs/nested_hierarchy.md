# Opt-in nested global/rack/host Gaussian variant

`nested-global-rack-host-v1` is a separate, disabled-by-default diagnostic variant.
It does not replace the original class-host research mode or the public two-level
rack-host variant. It requires an explicit `enabled=true` settings file and a
frozen public adjustment model using rack-level control eligibility. Hardware
classes are not added as another nested level.

## Deterministic host-weighted rack basis

For n monitored canaries in G represented racks, let C be the n by G rack
incidence matrix and D=diag(m), where m=C'1 contains monitored host counts.
Keep the frozen canary host order; sort rack columns by rack ID. Define

```text
Z = C D^(-1/2)
w = sqrt(m/n)
v = w - e_last
T = I - 2 v v' / (v'v)       (G > 1)
R = Z T[:, :G-1]
```

This fixed Householder construction has no random signs or arbitrary SVD choice.
Z'Z=I; T sends w to the last coordinate; therefore 1'R=0 and R'R=I. R has
shape n by (G-1), is constant within each rack and spans all rack-constant host
vectors orthogonal to the host all-ones vector. The one-rack case explicitly uses
an n by 0 R instead of dividing by a zero Householder vector.

The rack-level deviation map is A_r=D^(-1)C'R. Its rows map rack coordinates u
to each rack's actual deviation d=A_r u. C d=R u and m'd=0. This is a host-count-
weighted zero mean, not an unweighted sum across unequal racks. The two-rack
hand case with counts (2,1) gives R=(-1,-1,2)'/sqrt(6).

B reuses the deterministic within-rack orthonormal sum-zero basis from the
existing hierarchy helper. B is n by (n-G), C'B=0, B'B=I and R'B=0. Singleton
racks have no host-deviation coordinate. When every rack is a singleton, B has
zero columns. When only one host is represented, both R and B have zero columns.
The map [1,R,B] has rank n, with its global column having squared norm n and
all other columns orthonormal. The model's coordinates are consequently distinct.

All counts and constraints refer to monitored canaries. They are not silently
weighted by unmonitored world hosts or by request counts. Changing the monitored
roster changes the basis, priors and protocol fingerprint. Full matrices and
host/rack IDs are serialized with each result; numerical-library versions are
recorded. Tests verify host-space invariance after permutation and remapping.

## Joint state, dynamics and priors

```text
a = 1 g + R u + B b
s = [g, u, b, e]
F = blockdiag(rho_global, rho_rack I_(G-1), rho_host I_(n-G), Phi_e)
Q = blockdiag(sd_global^2, sd_rack^2 I_(G-1), sd_host^2 I_(n-G), Qe)
H = [1,R,B,I]
L = [1,R,B,0]
```

`state_transition` is F; `observation_map` is H; `effect_risk_map` is L.
Each level has its own explicit innovation SD, persistence and proper prior SD.
All SDs use log-latency units; covariance uses squared log latency. Rack and host
coordinate priors are isotropic within their respective orthonormal spaces.
Empty coordinate levels add no state or uncertainty. The declared rack SD is an
orthonormal-contrast coordinate SD, not a common per-rack marginal SD: unequal
rack sizes induce different marginal uncertainties.

At exposure, effect coordinates have independent zero-mean priors with variances
sigma_global squared, sigma_rack squared and sigma_host squared. The AR mean and
full covariance are carried from the no-effect preperiod filter. Define the rack
projector P_r=C D^(-1)C'. Then

```text
R R' = P_r - 11'/n
B B' = I - P_r
Cov(a) = sigma_global^2 11'
       + sigma_rack^2 (P_r - 11'/n)
       + sigma_host^2 (I - P_r)
```

The induced effect innovation covariance has the same expression with the three
innovation SDs. Both full matrices are exported. The original common Cholesky/
Joseph engine jointly filters all effect and AR coordinates, including every
posterior cross-covariance. Full white V, including control-estimation uncertainty,
is unchanged; it is not folded into AR Qe or added twice. Missing-minute, subset
observation and exposure-prior conventions are inherited from the public engine.

## Components and uncertainty

The result exposes scalar global mean/variance, rack-level deviation means/full
covariance, and host-space component means/full covariance for global, rack and
host deviations. It also returns total host mean/full covariance and the full
posterior state mean/covariance. `component_cross_covariances` contains all three
pairs: global/rack, global/host and rack/host, in fixed host order.

Total effect covariance is the sum of the three component covariance matrices
plus each cross-covariance and its transpose. Marginal variances alone are
insufficient. Tests independently condition the multivariate Gaussian, verify
reconstruction, and exercise unequal observation subsets to induce nonzero
cross-level covariance. Effect-risk calculations use L m and L P L', excluding
AR noise while preserving its role in observation inference.

The global coordinate g is a release-associated shared component of adjusted
canary residuals. The nuisance workload factor f_hat is estimated separately from
fresh unexposed controls before this filter runs. It is subtracted exactly once
by the frozen adjustment; f_hat is not g, and g is not another fitted control
factor. A global canary residual component can also reflect model mismatch,
remaining workload confounding or hardware effects. Its label does not establish
causal release attribution. Control contamination and unpropagated nuisance-
parameter uncertainty remain explicit challenges.

## Crossed hardware classes and racks

Hardware class and rack often overlap: one class appears in several racks and a
rack contains several classes. Neither partition is nested within the other.
Stacking global, rack, class and host as nested levels would impose false
constraints and potentially confound components. A crossed-effects model needs
its own incidence matrices, identifiable constraints, priors, selection protocol
and calibration. This variant accepts rack membership only; extra `levels`, class
grouping or threshold fields in its configuration are rejected. Class metadata
may remain public nuisance metadata; it is not an extra latent effect level.

## Selection/calibration gate and commands

No existing research/public policy is promoted to the nested variant. All nested
results have `validation_status=unselected_uncalibrated`, `inference_use=diagnostic_only`,
`development_selection_required=true` and `calibration_required=true`.
Observation eligibility retains the upstream 80% canary / three controls per
represented rack policy. Decision eligibility is always false. The inherited
uncalibrated score is exposed only as `diagnostic_score`; there is no generic
`score` output for the decision path. Thresholds and alarms are null. The API
accepts no old threshold or selection artifact, and configuration cannot switch
these requirements off. Dashboard monitoring remains disconnected.

The protocol fingerprint covers variant, settings, frozen nuisance model, host/
rack roster and basis. A future promotion patch must perform new development
selection for this variant, freeze its parameters and fingerprint, then perform
new calibration and independent null validation under that frozen protocol.
Use disjoint registered roles/seeds; do not reuse holdout tuning or thresholds
from the earlier variants. Dataset/generator and observation-distribution changes
also require an explicit reviewed protocol. This patch intentionally performs
no hyperparameter selection, threshold fitting or performance experiment.

```bash
python -m canary_ssm.nested_fixture --out examples/nested_hierarchy
python -m canary_ssm.nested_hierarchy --settings configs/hierarchy_nested_v1.json --model examples/grouped_hierarchy/model_rack.json --adjusted examples/grouped_hierarchy/adjusted_rack.json --out nested_diagnostic.json
python -m pytest -q tests/test_nested_hierarchy.py
```

The shipped settings file is an explicit example opt-in; no original entry point
loads it automatically. The saved public example reuses the earlier committed
algebraic rack fixture. Separate numerical fixtures cover counts (3,2,1), a
single rack, all-singleton racks and one host. Their CSVs contain basis errors
and component means/variances; JSON retains full covariance. Analytic cases
exercise the engine directly and do not represent calibrated decision policies.
No new randomness, development selection, calibration, physical-world power or
false-alert results are claimed. The nested component output budget is one
million T*n*n entries, in addition to the common engine's joint-state budget.
