# Version 2 Implementation — Detailed Technical & Experimental Summary

**Repository:** `C:\afml-exp\Implementation\canary_ssm_project`  
**Scope:** Strictly **Version 2** changes implemented on top of v1 (`v0.1-first-full-run`, commit `8472b2a`), spanning **Phase P0 (`v0.2-p0`, commit `ca0b37e`)**, **Phase P1 (`v0.3-p1`, commit `7eb2e8d`)**, and **Phase P1b (`wp-p1b-baselines` working branch)**.  
**Verification State:** `.venv\Scripts\python.exe -m pytest -q` freshly verified on `wp-p1b-baselines` -> **`107 passed in 98.50s` (exit code `0`)**.

---

## 1. Executive Overview: What Changed in V2 and What Happened

Version 2 upgrades the v1 codebase from a single mixed-regime prototype (which failed calibration gates on `S1_step` in `results/final/gate_status.json`) into a leakage-safe, regime-separated, reproducible benchmarking harness:

1. **Phase P0 (`ca0b37e`, `v0.2-p0`) — Infrastructure, Seed Registry, Provenance, and Deterministic Parallelism:**
   - Replaced ad-hoc seeding and single-threaded loops with a 1M-block deterministic seed registry (`canary_ssm/seeds.py`), full cryptographic manifest tracking (`canary_ssm/manifest.py`), and Windows-safe deterministic multiprocessing with JSONL resume checkpoints (`canary_ssm/parallel.py`).
   - **Experiment `X-0.1`:** Reproduced the full v1 evaluation (`1,000` test rollouts) with 1 worker (`538.401s`) vs 8 workers (`142.456s`, **3.78x speedup**), achieving **bitwise-identical** `per_rollout_metrics.csv` SHA-256 checksums and `0` fit failures.

2. **Phase P1 (`7eb2e8d`, `v0.3-p1`) — Protocol Repair, Anomaly Diagnoses, Cross-Validated Grid Tuning, and 14k-Null Gate G2 Validation:**
   - Separated mixed plain+step benchmarks into dedicated configs (`configs/plain_main.yaml`, `configs/step_regime.yaml`) and introduced Policy Schema v2 with regime enforcement and `require_tuned()` guards in `canary_ssm/studies/`.
   - **Experiment `X-0.2(a)`:** Proved `hier_arwhite` collapses onto `hier_ssm` when `meas_sd=0.0` (optimizer hits white-variance lower bound `0.0001`; score median diff `0.000312`), whereas under `meas_sd=0.01` it recovers `v ≈ 0.0086–0.0099` and diverges (`0.1567` median max-abs diff).
   - **Experiment `X-0.2(b)`:** Resolved the v1 Experiment 7 `6.8%–9.0%` step-null FAR anomaly—confirming `>=99.8%` regime-selector accuracy and showing that recalibrating at `B=2000, n=2000` brings **all 8 `(regime, method)` cells** into exact Beta-Binomial Gate G2 compliance (`bb_p = 0.0299..0.9422`).
   - **Experiment `X-0.2(c)`:** Refuted naive label-error invariance via a `sd_h_ratio x label_error` factorial grid on `S2_class_wide`, showing monotonic capped-delay degradation (`1.45 -> 5.075 -> 6.365` min at `sd_h_ratio=1.0`) and posterior energy redistribution toward local effects.
   - **Experiment `X-0.3`:** Implemented 5-fold CV + 1-SE selection + automatic edge expansion (`v2.0 -> v2.0-exp2` in `configs/grids_v2.yaml`). All classical baselines + `pooled_ssm` + `indep_ssm` converged strictly inside interior grid bounds; `hier_ssm` moved to `rho=0.999` and lower edge `sd_g=0.000125, prior_sd=0.005` (`dev_capped_time = 13.68` min, matching the random-walk limit `hier_rw` at `13.62` min).
   - **Experiment `X-0.4`:** Calibrated on `B=2000` plain nulls and validated across `14,000` plain nulls/method (`2000` per family across `7` families = `119` cells). **`118 / 119` cells passed Gate G2**; all 17 methods passed global calibration (`4.29%–5.41%`, `bb_p = 0.1689..0.9880`) and KS/Mann–Whitney exchangeability (`p >= 0.045`). Only ablation `hier_rank0` failed on `S5_label_errors` (`193/2000 = 9.65%`, `bb_p = 1.22e-8`), verified as unadjusted factor shock pooling onto imbalanced `[6,4]/[8,2]` class splits under random label flips.

3. **Phase P1b (`wp-p1b-baselines`, uncommitted working branch) — Extra Literature Baselines (`WP-E1`) & Clairvoyant Oracles (`WP-E2`):**
   - Implemented 7 new strictly causal sequential baselines (`wmean`, `ar_cusum`, `glr_window`, `sparse_mix_glr`, `bocpd`, `msprt`, `mw_judge`) with causal AR(1) prewhitening across missing gaps and parity candidate grids (`<= 24` candidates) in `configs/grids_v2.yaml`.
   - Implemented 3 clairvoyant upper-bound oracles (`oracle_cusum`, `oracle_bayes`, `oracle_subset`) and `efficiency_ratio`, gated by `--oracles` and isolated from non-oracle rankings.
   - Added 10 P1b unit tests (`tests/test_p1b_baselines.py`); full test suite grew from `41` (v1) -> `75` (P0) -> `97` (P1) -> **`107` (P1b)**, all passing.
   - **Pending Future Work (Phases P2–P4):** Scaled `evaluate` benchmarks and full `E1..E8`, `R1..R8`, `G1..G8`, `RT-1..RT-3` study campaigns from `Canary_SSM_Change_Plan.pdf` have **not** been executed yet.

---

## 2. Phase P0 (`ca0b37e`, `v0.2-p0`): Engineering Housekeeping & `X-0.1`

### 2.1 Code & Architecture Changes (`12` files)
- **`canary_ssm/seeds.py`** (`REGISTRY_VERSION = "2.0"`): Enforces non-overlapping `BLOCK = 1_000_000` seed spaces (`FAMILY_STRIDE = 20_000`, up to `50` families/block) across `smoke` (`10_000`), `dev` (`1_000_000`), `calibration` (`2_000_000`), `null_validation` (`3_000_000`), `test` (`4_000_000`), `stress` (`5_000_000`), `audit` (`6_000_000`), `noise_sweep` (`7_000_000`), `study_R1..R9`, `study_E2..E8`, `study_X`, `realtrace`, `study_regime`, `study_robust`, plus documented legacy v1 seed ranges.
- **`canary_ssm/manifest.py`**: Records git commit/dirty flag/branch/tag (with Windows MinGit discovery via `find_git`), config & grid SHA-256 hashes, candidate-table hash, model/policy/lockfile hashes, Python & package versions, OS/CPU specs, disk headroom, wall times, and fit failure counts.
- **`canary_ssm/parallel.py`**: Implements `default_workers()` (`max(1, cpu_count - 2)`), `resolve_workers()` (avoids spawn overhead when `n_items < 20`), `_worker_init()` pinning `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, and `NUMEXPR_NUM_THREADS` to `1` per worker, `pmap` deterministic ordering, JSONL resume journals, and disk budget checks.
- **CLI / Experiments / Tasks:** Updated `canary_ssm/{cli,experiments,preprocess,schema,simulate}.py` and added `tasks.ps1` / `tasks.sh`.
- **Tests Added (`+34` -> `75` total):** `tests/test_kalman_properties.py` (`1` Hypothesis property test) and `tests/test_p0_housekeeping.py` (`33` tests).

### 2.2 Experiment `X-0.1`: Parallelism Determinism & Scaling
Evaluated the v1 frozen artifact set (`artifacts/model`, `artifacts/policy`, `model_hash=780b41c728c091a8`, `policy_hash=9c0231d75f61673b`) on `test` (`n_pairs=500`, `1,000` rollouts, `seed_base=4000000`) with `workers=1` vs `workers=8`:

| Run | Workers | Wall Time (`evaluate_s`) | Speedup | Fit Failures | `per_rollout_metrics.csv` SHA-256 |
|---|---:|---:|---:|---:|---|
| `results/x01/w1` | 1 | `538.401 s` | `1.00x` | `0` | `A2B3E3801745CFDCF055A7D6595DFB54CD534DC6D09804945BABDF6157A3687F` |
| `results/x01/w8` | 8 | `142.456 s` | **`3.78x`** | `0` | `A2B3E3801745CFDCF055A7D6595DFB54CD534DC6D09804945BABDF6157A3687F` (**exact match**) |

---

## 3. Phase P1 (`7eb2e8d`, `v0.3-p1`): Protocol Repair, Diagnostics & `X-0.2..X-0.4`

### 3.1 Code & Protocol Changes (`24` files)
- **Regime Separation:** Split `configs/default.yaml` into `configs/plain_main.yaml` (`regime: plain`, 7 families totaling weight `1.0`: `S1_sparse 0.24`, `S2_class_wide 0.24`, `S3_broad 0.12`, `S4_weak_sparse 0.12`, `S5_label_errors 0.12`, `single_canary 0.12`, `transient 0.04`) and `configs/step_regime.yaml` (`regime: step`, same weights with `workload_step: 0.3365`); preserved `configs/legacy_mixture_with_step.yaml` for historical reproduction.
- **Policy Schema v2 & Guardrails:** Updated `canary_ssm/decision.py`, `experiments.py`, `metrics.py`, `report.py`, and created `canary_ssm/studies/{__init__,study_anomalies,study_regime,study_robust}.py` enforcing `require_tuned(model_cfg)` (`kind == 'tuned'`) and `require_regime(policy, expected)`.
- **Predeclared Hyperparameter Tuning (`grids_v2.yaml`):** Implemented 5-fold cross-validation + 1-SE selection + automatic boundary expansion (`v2.0 -> v2.0-exp1 -> v2.0-exp2`) on `dev` (`500` pairs) and exact Beta-Binomial two-sided validation (`Gate G2`: `p >= 0.01` with multiplicity allowance and rate `<= 0.075` for `n >= 2000`).
- **Tests Added (`+22` -> `97` total):** `tests/test_p1_protocol.py` (`22` tests).

### 3.2 Experiment `X-0.2(a)`: Diagnosis of `hier_arwhite` vs `hier_ssm`
From `results/x02/x02a/{x02a_nuisance_comparison,x02a_summary}.csv`:

| World | Class | `phi_main` | `phi_arwhite` | `q_main` | `q_arwhite` | `v_main` | `v_arwhite` | Boundary Hit (`arwhite`) | Median Max-Abs Score Diff (`50` rollouts) | Max Score Diff |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| `meas_sd=0.0` | 0 | `0.605893` | `0.605940` | `0.019977` | `0.019977` | `0.000100` | `0.000101` | `False` | `0.000312` | `0.000701` |
| `meas_sd=0.0` | 1 | `0.605315` | `0.605319` | `0.019961` | `0.019961` | `0.000100` | `0.000100` | **`True`** | *(same)* | *(same)* |
| `meas_sd=0.01` (`40` dev) | 0 | `0.522023` | `0.602974` | `0.023004` | `0.020008` | `0.000100` | **`0.009918`** | `False` | **`0.156727`** | **`0.431731`** |
| `meas_sd=0.01` (`40` dev) | 1 | `0.523414` | `0.581811` | `0.022998` | `0.020813` | `0.000100` | **`0.008582`** | `False` | *(same)* | *(same)* |

**Takeaway:** Under `meas_sd=0.0`, the `ar_white` MLE hits the optimizer lower boundary (`v = 1e-4`), making `hier_arwhite` mathematically indistinguishable from `hier_ssm` (`ar_only`, `v = 1e-4`). Under `meas_sd=0.01`, `ar_white` genuinely identifies `v ≈ 0.0099 / 0.0086` and produces distinct scores (`NLL = -195881` vs `-195781` on class 0). Hence `hier_arwhite` is treated as redundant at `meas_sd=0` and reserved for `meas_sd > 0` stress studies.

### 3.3 Experiment `X-0.2(b)`: Diagnosis of Step-Regime `6.8%–9.0%` Anomaly
From `results/x02/x02b/x02b_summary.md` & CSVs:
1. **Regime-Selector Accuracy:** On `v1_exp7_1000_eval_nulls`, selector classified plain `500/500 (100.0%)` and step `499/500 (99.8%)`. On a fresh `4,000`-per-regime check (`beta_jitter=0.03`, `step_workload_step=0.3365`, `sd_host=0.02`), selector classified plain `3997/4000 (99.92%)` and step `3998/4000 (99.95%)`.
2. **Recalibration at `B=2000, n=2000`:** In v1 Exp 7 (`B=500, n=500`), causal dual-regime rates reached `9.0%` (`adj_cusum`, `bb_p=0.0121`), `7.6%` (`topk_cusum`, `bb_p=0.0875`), and `6.8%` (`hier_ssm`, `bb_p=0.2231`) solely due to `B=500` order-statistic threshold variance (`k=476/500`). Recalibrating with `B=2000` (`k=1901`) resolved the anomaly cleanly across all 8 cells (all pass Gate G2, KS `p = 0.1201..0.9348`, MW `p = 0.0212..0.6948`):

| Regime | Method | Cal Threshold (`B=2000`) | Alerts (`n=2000`) | Achieved FAR | 95% CI | `bb_pvalue_two_sided` | Pass G2 |
|---|---|---:|---:|---:|---|---:|---|
| `plain` | `matched_contrast` | `1.1526` | 86 | `0.0430` | `[0.0345, 0.0528]` | `0.3290` | `True` |
| `plain` | `adj_cusum` | `58.1813` | 132 | `0.0660` | `[0.0555, 0.0778]` | `0.0299` | `True` |
| `plain` | `topk_cusum` | `111.8070` | 111 | `0.0555` | `[0.0459, 0.0665]` | `0.4356` | `True` |
| `plain` | `hier_ssm` | `-0.8332` | 118 | `0.0590` | `[0.0491, 0.0702]` | `0.2089` | `True` |
| `step` | `matched_contrast` | `1.2044` | 90 | `0.0450` | `[0.0363, 0.0550]` | `0.5036` | `True` |
| `step` | `adj_cusum` | `125.5590` | 101 | `0.0505` | `[0.0413, 0.0610]` | `0.9422` | `True` |
| `step` | `topk_cusum` | `241.1430` | 82 | `0.0410` | `[0.0327, 0.0506]` | `0.1970` | `True` |
| `step` | `hier_ssm` | `-0.6722` | 94 | `0.0470` | `[0.0381, 0.0572]` | `0.7130` | `True` |

### 3.4 Experiment `X-0.2(c)`: Label-Error Invariance & `sd_h_ratio`
From `results/x02/x02c/x02c_summary.md` (`n_null=200, n_harm=200` on `S2_class_wide`):
- Under `sd_h_ratio = 0.25`: label corruption `{0.0, 0.3, 0.5}` degrades `mean_capped_time` `1.145 -> 4.160 -> 5.730` min (`host_auc_at30`: `0.9990 -> 0.9816 -> 0.9786`), while `post_class_energy_frac` drops `0.9507 -> 0.7651 -> 0.7034`.
- Under `sd_h_ratio = 1.00`: `mean_capped_time` degrades `1.450 -> 5.075 -> 6.365` min (`success_rate`: `1.00 -> 0.985 -> 0.980`; `post_local_energy_frac` rises `0.0598 -> 0.2737 -> 0.3412`).
- Under `sd_h_ratio = 4.00`: baseline delay starts slower (`20.89 -> 25.62 -> 24.84` min; `success_rate`: `0.925 -> 0.915 -> 0.930`) and the posterior shifts predominantly to local deviations under mislabeling (`post_local_energy_frac`: `0.2045 -> 0.5194 -> 0.5939`).

### 3.5 Experiment `X-0.3`: K-Fold + 1-SE Tuning & Edge Checks (`artifacts/model_v2`)
From `artifacts/model_v2/{model_config.json,edge_selection.csv,fit_failures.csv,nuisance_main.json}` & `results/x03/x03_profiles.csv`:
- **Nuisance fit (`nuisance_main.json`, `1,500` series/class, `ar_only`):** Recovered `phi_e = [0.6005, 0.5996]`, `q_e = [0.01993, 0.01994]`, `class_lambda = [0.01562, 0.01561]`, `0` boundary hits, `0` fit failures (`fit_failures.csv` empty).
- **Selected Hyperparameters (`v2.0-exp2`, `grid_hash=96e474e08543dd7e`):**
  - `matched_contrast`: `window=30` (argmin `15`; `dev_capped_time = 46.65` min; `loc_cutoff=4`; interior)
  - `adj_ewma`: `alpha=0.05` (`71.19` min; `loc_cutoff=5`; interior)
  - `adj_cusum`: `k=0.75` (`44.75` min; `loc_cutoff=4`; interior)
  - `topk_cusum`: `K=5, k=1.0` (argmin `K=10, k=1.0`; `29.90` min; `loc_cutoff=4`; interior)
  - `pooled_ssm`: `rho=0.99, sd_g=0.001, prior_sd=0.005` (`35.32` min; `loc_cutoff=9`; interior)
  - `indep_ssm`: `rho=0.995, sd_g=0.0005, prior_sd=0.01` (`19.54` min; `loc_cutoff=4`; interior)
  - `hier_ssm`: `rho=0.999` (interior `[0.9, 0.9995]`), **`sd_g=0.000125` (low edge)**, **`prior_sd=0.005` (low edge)** (`13.68` min; `loc_cutoff=4`)
  - `hier_rw`: `rho=0.9999`, **`sd_g=0.0001` (low edge)**, **`prior_sd=0.01` (low edge)** (`13.62` min; `loc_cutoff=4`) — confirming `hier_ssm` moves cleanly toward the persistent step asymptote.
  - `hier_no_persist`: `rho=0.0, sd_g=0.01`, **`prior_sd=0.01` (low edge)** (`70.26` min; `loc_cutoff=6`).

### 3.6 Experiment `X-0.4`: Plain-Regime Calibration (`B=2000`) & Gate G2 (`14,000` Nulls/Method)
From `results/x04/{gate_status.json,x04_summary.md,exchangeability_audit.csv}` & `artifacts/policy_plain/null_validation.json`:
- **Calibration:** `B = 2000` plain nulls (`seeds 2000000..2001999`), threshold order statistic `k = 1901` (`alpha = 0.05`).
- **Validation:** `per_family = 2000` across all 7 plain families = `14,000` nulls/method (`119` cells total).
- **Global FAR & Exchangeability (`17 / 17` methods):**
  - Primary methods global FAR (`n=14,000`): `matched_contrast = 0.0477` (`bb_p=0.688`), `adj_ewma = 0.0541` (`bb_p=0.428`), `adj_cusum = 0.0509` (`bb_p=0.837`), `topk_cusum = 0.0436` (`bb_p=0.215`), `pooled_ssm = 0.0488` (`bb_p=0.848`), `indep_ssm = 0.0501` (`bb_p=0.955`), `hier_ssm = 0.0476` (`bb_p=0.667`).
  - Dual-mode combos: `combo_hier_topk = 0.0499` (`bb_p=0.988`), `combo_hier_m0 = 0.0471` (`bb_p=0.597`), `combo_m0_topk = 0.0491` (`bb_p=0.902`).
  - Exchangeability (`cal n=2000` vs `val n=14000`): all 17 methods passed KS (`p = 0.0767..0.9514`) and Mann–Whitney (`p = 0.0455..0.9902`).
- **Per-Cell Gate G2 (`118 / 119` pass):**
  - Every primary method, combo detector, and 5/6 ablations passed all 7 families (`112/112` cells, minimum `bb_p = 0.035057`).
  - **Single failing cell (`status = "FAIL"` in `gate_status.json`):** `S5_label_errors x hier_rank0` -> **`193 / 2000 = 0.0965`** (`95% CI [0.08391, 0.11029]`, expected `99.95`, `bb_pvalue_two_sided = 1.218e-08`).
  - **Root cause:** A 400-null diagnostic check verified that when `30%` label noise flips 3/10 canary labels, balanced `[5,5]` classes become `[6,4]` or `[8,2]`. Because `hier_rank0` sets `factor_rank=0`, the `+5%` shared shock (`log(1.05)`) stays in residuals and pools across more hosts in larger classes (`max_cls==6`: `27/330 = 8.18%`; `max_cls==8`: `21/70 = 30.00%`). All factor-adjusted models pass cleanly.

---

## 4. Phase P1b (`wp-p1b-baselines` Working Branch): Additional Baselines & Oracles

### 4.1 `WP-E1` Additional Comparators (`canary_ssm/baselines_extra.py`, `canary_ssm/factor.py`, `docs/baselines.md`)
- Extended `Adjusted` in `canary_ssm/factor.py` with optional `ctl_r` and `ctl_class_id` arrays so residual-scale nonparametric judges share identical pre-period and factor inputs.
- Implemented `_prewhiten(z, phi)` providing exact causal AR(1) prewhitening across arbitrary missing gaps (`e[t] = (z[t] - phi^delta * z[t_prev]) / sqrt(1 - phi^(2*delta))`) and 7 literature baselines in `canary_ssm/baselines_extra.py` (`EXTRA_BASELINES`, `PREWHITENED_BASELINES`), each restricted to `<= 24` candidates in `configs/grids_v2.yaml`:
  1. `wmean`: Stateless trailing `w`-minute standardized top-`K` mean (`w in {5,10,15,30,45} x K in {1,3,5}`, 15 candidates).
  2. `ar_cusum`: Page CUSUM on AR(1)-prewhitened innovations with scaled drift `k_pw = k * sqrt((1-phi)/(1+phi))` (`k in {0.1,0.25,0.5,0.75}`, 4 candidates).
  3. `glr_window`: Lai (1995) / Siegmund–Venkatraman sliding-window one-sided normal GLR (`W in {15,30,45,60} x K in {1,3,5}`, 12 candidates).
  4. `sparse_mix_glr`: Xie & Siegmund (2013) multi-stream mixture GLR computed in log-sum-exp space (`p0 in {0.1,0.3,0.5} x W in {30,60}`, 6 candidates).
  5. `bocpd`: Adams & MacKay (2007) Bayesian Online Changepoint Detection with conjugate Normal–Gamma predictive updates and directional post-onset shift mass `mu > 0` (`lambda_h in {60,120,240}`, 3 candidates).
  6. `msprt`: Johari, Pekelis & Walsh (2017/2022) always-valid mixture SPRT (`tau in {0.25,0.5,1.0,2.0}`, 4 candidates).
  7. `mw_judge`: Kayenta-style sliding Mann–Whitney U normal approximation comparing class-aligned canary vs control residuals (`w in {15,30}`, 2 candidates).

### 4.2 `WP-E2` Clairvoyant Upper-Bound Oracles (`canary_ssm/oracles.py`, `experiments.py`, `cli.py`, `report.py`)
- Implemented `ORACLE_METHODS = ("oracle_cusum", "oracle_bayes", "oracle_subset")` and `efficiency_ratio(method_capped, oracle_capped, miss_capped)` (normalized capped-time shortfall in `[0, 1]`):
  - `oracle_cusum`: CUSUM restricted to true affected hosts with optimal `k = delta / (2 * sigma_i)`.
  - `oracle_bayes`: Independent SSM initialized with true nuisance parameters and `prior_sd = delta`, `rho = 1.0`.
  - `oracle_subset`: Independent SSM restricted to the true affected host indices.
- Wired behind explicit `--oracles` CLI flag on `calibrate`, `validate-null`, and `evaluate`, with `ORACLE` labeling so oracles never appear in real-method rankings.

### 4.3 Test Verification & Remaining Unrun Scope
- Added `tests/test_p1b_baselines.py` (`10` tests covering causality, missing gaps, constant-shift behavior, budget `<= 24`, oracle gating/isolation, and CLI wiring).
- Full suite `.venv\Scripts\python.exe -m pytest -q`: **`107 passed in 98.50s` (exit code `0`)**.
- **Unrun v2 Work (`Canary_SSM_Change_Plan.pdf` Phases P2–P4):** Scaled benchmark runs evaluating P1b comparators and oracles plus full studies `E1..E8`, `R1..R8`, `G1..G8`, and `RT-1..RT-3` have **not** been executed yet.
