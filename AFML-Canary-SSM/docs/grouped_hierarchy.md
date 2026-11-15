# Joint class/host and explicit rack/host hierarchy

The original research implementation in `hierarchy.py`, including its class-host
basis, effect model, filtering conventions and experiment call paths, is
unchanged. The new `public_hierarchy` adapter reuses `class_structure` and the
common joint Gaussian engine on public adjusted observations. Its default is
`group_by=class_id`, variant `public-class-host-v1`. A physical-rack demo requires
explicit `group_by=rack_id`, variant `demo-rack-host-v1`. No fault labels or
scheduler fields select groups or influence inference.

## Fixed roster and constrained basis

For n monitored canaries and G represented groups, C has shape n by G, with a
single 1 in each row. Group columns are sorted by their class/rack ID. Input host
order is preserved exactly; rows are never sorted by group. `grouped_structure`
rejects duplicate host IDs, malformed labels and conflicting grouping. Public
canary IDs and immutable placement come from the frozen development model.
A run cannot substitute a different host order after structure construction.

B has shape n by (n-G). It places an orthonormal null-space basis within each
group using the existing research helper. C'B=0 and B'B=I. For a singleton, no
local basis column is added and that host's deviation is exactly zero. All
singletons give an n by 0 B. Within-group sums are over monitored canaries,
not over controls or unmonitored hosts in the physical rack.

A basis can rotate or change signs under reordering or numerical-library changes.
Its serialized matrices, group IDs and host IDs identify the actual coordinates.
With the declared isotropic within-group priors/dynamics, total host inference is
invariant to orthonormal basis rotations and host permutations after mapping
back to host IDs. Tests verify this in host space. b coordinates are not themselves
individual host deviations; the reported host deviation is B b.

## Joint state, prior and dynamics

```text
a = C theta + B b
s = [theta, b, e]
F = blockdiag(rho_g I_G, rho_h I_(n-G), Phi_e)
Q = blockdiag(sd_g^2 I_G, sd_h^2 I_(n-G), Qe)
H = [C, B, I_n]
L = [C, B, 0]
r = H s + epsilon; epsilon ~ N(0,V_t)
```

`state_transition` is F, `observation_map` is H and `effect_risk_map` is L.
`effect_map` is [C,B], the map from effect coordinates alone. All updates use one
joint Kalman filter and full covariance, including theta/b/e cross terms. V
retains shared control uncertainty; Qe is the separate AR process covariance.
The existing Cholesky/Joseph engine and missing-minute predictions are reused.

At exposure the coordinate prior is

```text
P_effect = blockdiag(prior_group_sd^2 I_G, prior_deviation_sd^2 I_(n-G))
P_s = blockdiag(P_effect, P_e_carried)
Cov(a) = prior_group_sd^2 C C' + prior_deviation_sd^2 B B'
```

The full AR preperiod state is carried into rollout. Effect priors first exist
at exposure, using the public adapter's prior-before-exposure-observation
convention. The legacy research wrapper's preceding-step convention remains
unchanged. No pre-exposure effect output is produced. Receipt-time guards and
fixed healthy-development noise are inherited from `public_filter`.

For group size m, B B' within the group equals I-J/m. Thus prior marginal
variance is sigma_g squared + sigma_b squared (1-1/m), and a pair's covariance
is sigma_g squared - sigma_b squared/m. Cross-group prior covariance is zero;
posterior cross-group covariance can arise from shared white control uncertainty.
The induced effect innovation covariance has the same expression with sd_g and
sd_h. Both full matrices are returned explicitly.

These covariances and the two persistence coefficients induce pooling. A shared
group state can transmit evidence from one host to a peer; separate group and
local persistence change how shared and contrasting evidence decay. This is not
a list of independent per-host filters. Group labels alone do not guarantee
pooling: for equal-sized groups, a size-scaled diagonal induced prior/process
covariance plus identical persistence can recover independent host behavior.
The saved negative control deliberately demonstrates that case. Some parameter
choices imply negative within-group covariance rather than positive borrowing;
parameters must be declared and validated, not interpreted by model name alone.

The rack demo config uses a stronger shared prior and smaller local innovation
SD with different persistence; these are declared acceptance/demo settings,
not fitted or tuned detector hyperparameters. The class config preserves the
original coordinate-scale defaults. Original research model artifacts and
class-based algorithms are byte-preserved.

## Separate outputs and risk

The output contains group IDs and `group_effect_label=class_effect` or
`rack_effect`, and separately reports:

| Output | Meaning |
| --- | --- |
| `group_effect_mean/covariance` | theta, one component per represented class/rack |
| `host_group_effect_mean/covariance` | C theta, in fixed host order |
| `host_deviation_mean/covariance` | B b, within-group sum-zero host deviations |
| `group_deviation_cross_covariance` | Cov(theta, B b), needed to reconstruct total covariance |
| `total_host_effect_mean/covariance` | C theta + B b, including all cross terms |
| `posterior_state_mean/covariance` | Full joint theta/b/e posterior |
| `effect_coordinate_covariance` | Joint theta/b block including off-diagonals |
| `induced_effect_prior_covariance` | [C,B] P_effect [C,B]' at exposure |
| `induced_effect_innovation_covariance` | [C,B] Q_effect [C,B]' |

Total covariance cannot be reconstructed by adding two marginal covariances
alone: include both group/deviation cross terms. Tests verify the reconstruction
and independent Gaussian conditioning, including a singleton and noncontiguous
groups. AR noise remains in observation inference but is absent from L. Tail
risk uses only L m and L P L', not H m or H P H'. A test changes the AR coordinates
without changing effect-risk projections.

The inherited release score is log maximum host Pr(a_i>KAPPA), conditional on
fixed parameters and the Gaussian model. It is not Pr(any host harmful), a fault
label, causal attribution or a calibrated release alarm. Thresholds/alarms are
null; dashboard monitoring remains disconnected. Existing background-control
contamination and nuisance-uncertainty limitations remain open.

## Eligibility and entry points

Grouping must match the frozen adjustment policy. Rack effect inference cannot
reuse class-only control support, and class inference cannot silently reinterpret
rack policy. Defaults remain 80% fresh observed canaries, three fresh unexposed
controls per represented group and 60 pre-windows for loading adaptation. A rack
with inadequate local controls makes that decision ineligible. No thresholds or
control rules are relaxed by this adapter.

```bash
python -m canary_ssm.hierarchy_fixture --out examples/grouped_hierarchy
python -m canary_ssm.public_hierarchy --model examples/grouped_hierarchy/model_rack.json --adjusted examples/grouped_hierarchy/adjusted_rack.json --group-by rack_id --settings configs/hierarchy_rack.json --out rack_posterior.json
python -m canary_ssm.public_hierarchy --model examples/grouped_hierarchy/model_class.json --adjusted examples/grouped_hierarchy/adjusted_class.json --out class_posterior.json
python -m pytest -q tests/test_public_hierarchy.py tests/test_public_filter.py tests/test_hierarchy_factor.py
```

`group_by=rack_id` is explicit through the CLI/config and the versioned variant.
The exported example has four monitored canaries, two in each rack, and three
candidate-independent controls per rack. It refits nuisance parameters on the
existing healthy development public input for that roster and changes no holdout
or threshold data. It re-emits saved algebraic metrics as a new committed public
slice with an explicit four-host exposure cohort. Its one-minute records represent
synthetic sufficient statistics. No new RNG seeds or physical-resource benchmark
are introduced. The physical-world topology can supply the same public interface;
world-latency Gaussian model adequacy remains unverified.

`pooling.csv` gives an independent-versus-hierarchy acceptance comparison with
diagonal white measurement noise and matched marginal prior variances. Peer
borrowing cannot be explained by a shared telemetry reference in this check.
It also saves the deliberately unpooled hierarchy negative control. A separate
test starts from diagonal host priors and demonstrates pooling created by distinct
group/local dynamics. The example manifest records hashes, parameters, versions,
machine, timing and computed gates. No false-alert or detection-power result is
reported. Joint covariance retention is bounded by the existing public input
budget and an eight-million-entry joint covariance limit.
