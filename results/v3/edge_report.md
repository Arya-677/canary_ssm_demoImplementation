# Edge Selection and Grid Expansion Report — Phase 1 (model_v3)

**Date:** 14 November 2026  
**Artifact Directory:** `artifacts/model_v3`  
**Dev Role:** `data/plain/dev` (500 pairs, 1000 rollouts)

---

## 1. Grid Expansion History
Grid selection followed the predeclared 5-fold cross-validation with 1-SE rule and up to two auto-expansions (`v2.0 -> v2.0-exp1 -> v2.0-exp2`):
- **Base Grid (`v2.0`):** Step 0
- **Expansion 1 (`v2.0-exp1`):** Extended boundary parameters across primary methods.
- **Expansion 2 (`v2.0-exp2`):** Final allowed expansion per preregistered protocol.

## 2. Final Selection Edge Status (`v2.0-exp2`)

All primary baselines resolved to interior parameter choices:
- `matched_contrast`: `window = 30.0` (range: [1.0, 45.0], interior)
- `adj_ewma`: `alpha = 0.05` (range: [0.02, 0.5], interior)
- `adj_cusum`: `k = 0.75` (range: [0.1, 1.5], interior)
- `topk_cusum`: `K = 5.0, k = 1.0` (interior)
- `wmean`: `w = 45.0, K = 3.0` (interior)
- `ar_cusum`: `k = 0.75` (range: [0.1, 1.125], interior)
- `glr_window`: `W = 45.0, K = 3.0` (interior)
- `sparse_mix_glr`: `p0 = 0.1, W = 60.0` (interior)
- `msprt`: `tau = 1.0` (range: [0.25, 2.0], interior)
- `mw_judge`: `w = 45.0` (range: [15.0, 68.0], interior)
- `pooled_ssm`: all parameters interior (`rho = 0.99, sd_g = 0.001, prior_sd = 0.005`)
- `indep_ssm`: all parameters interior (`rho = 0.995, sd_g = 0.0005, prior_sd = 0.01`)

### Boundary Hits and Asymptotic Explanations
Six parameter selections remain at grid edges after two expansions, all corresponding to documented physical/asymptotic behaviors:
1. `hier_ssm.sd_g = 0.000125` (low edge): Matches the near-constant shift / random-walk asymptote (`hier_rw`), reflecting that sustained regressions in the simulator are best modeled by minimal process innovation variance.
2. `hier_ssm.prior_sd = 0.005` (low edge): Low initial prior variance matches the known tight pre-period calibration and nests the subsequent `hier_ts` grid.
3. `bocpd.lambda_h = 960.0` (high edge): In Bayesian Online Changepoint Detection, large hazard parameter $\lambda_h$ represents the prior belief that changepoints are rare events ($1 / \lambda_h$), matching the canary evaluation setting where rollouts are predominantly healthy or have a single sustained event.
4. `hier_no_persist.prior_sd = 0.01` (low edge): Ablation model without AR persistence.
5. `hier_rw.sd_g = 0.0001` (low edge): Random-walk ablation lower bound.
6. `hier_rw.prior_sd = 0.01` (low edge): Random-walk ablation initial prior bound.

## 3. Nesting Verification
- `hier_ts` nesting check against `hier_ssm` parameters (`rho_g=0.999, rho_h=0.999, sd_g=0.000125, prior_sd=0.005`): **PASSED** (`nests_hier_ssm == True`).
- Candidate budget parity ($n_{\text{hier\_ts}} = 28 \le n_{\text{hier\_ssm}} = 42$): **PASSED**.
