# X-0.4 Plain-Regime Calibration Validity Summary

- **Model:** `artifacts/model_v2` (`kind=tuned`, `grid_version=v2.0-exp2`, `grid_hash=96e474e08543dd7e`)
- **Calibration set:** `data/plain/calibration` (`B = 2000` plain nulls, seeds `2000000..2001999`)
- **Validation set:** `data/plain/null_validation` (`per_family = 2000` across 7 families = `14,000` plain nulls, `--generate-on-the-fly`)
- **Gate criterion (Gate G2):** exact Beta-Binomial two-sided $p \ge 0.01$ (with Binomial multiplicity allowance) and achieved rate $\le 0.075$ for all cells with $n \ge 2000$.

## Global Summary (N = 14,000 nulls per method)
Every primary detector, `combo_*` detector, and 5/6 ablations calibrated within `[0.043, 0.054]` globally (`bb_p = 0.1689 .. 0.9880`) and passed the two-sample exchangeability audit (`KS p = 0.077 .. 0.951`, `MW p = 0.045 .. 0.990`).

## Gate G2 Outcome (`gate_status.json`)
- **Total cells:** `119` (`17` methods x `7` families, all `evaluable_cells = 119`)
- **Passing cells:** `118 / 119` (minimum `bb_p` across all 112 non-`hier_rank0` cells = `0.035057`)
- **Single failing cell:** `S5_label_errors` x `hier_rank0` -> `193 / 2000 = 0.0965` (`CI [0.0839, 0.1103]`, `expected_alerts = 99.95`, `bb_pvalue_two_sided = 1.218e-08`).

## Root-Cause Verification for `hier_rank0` on `S5_label_errors`
In a 400-null follow-up check on `S5_label_errors` (`seeds 3080000..3080399`), randomly flipping 3 of 10 `[0,1]` canary class labels turns `[5,5]` class counts into imbalanced splits (`6/4` or `8/2`). Because `hier_rank0` omits rank-1 factor subtraction (`factor_rank = 0`), the +5% shared shock (`log(1.05)`) stays in the residuals and pools across more hosts in larger classes:
- `max_cls == 6` (`n=330`): `27/330 = 0.0818` false alerts
- `max_cls == 8` (`n=70`): `21/70 = 0.3000` false alerts

All rank-1 factor-adjusted detectors (including `hier_ssm`, `indep_ssm`, `pooled_ssm`, `hier_degraded`, and all baselines) pass G2 across all 7 families and are cleared for Phase P1b / Tier 1.
`hier_rank0` fails exchangeability under imbalanced/noisy class splits and is excluded from S5 equal-FAR comparisons.
