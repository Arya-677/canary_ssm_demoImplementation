# X-0.2(b) Diagnosis: Step-Regime 6.8%-9.0% Anomaly

_Generated strictly from saved CSV/JSON outputs._


## v1 Experiment 7 Exact Beta-Binomial Audit (B=500, n=500)

| true_regime   | method           | policy             |   alerts |   n |   rate |   expected_alerts |   bb_sd |   p_upper |   p_lower |   bb_pvalue_two_sided |
|:--------------|:-----------------|:-------------------|---------:|----:|-------:|------------------:|--------:|----------:|----------:|----------------------:|
| plain         | matched_contrast | causal_dual_regime |       19 | 500 |  0.038 |           24.9501 |  6.8752 |    0.8251 |    0.2205 |                0.4411 |
| plain         | matched_contrast | single_threshold   |       19 | 500 |  0.038 |           24.9501 |  6.8752 |    0.8251 |    0.2205 |                0.4411 |
| plain         | adj_cusum        | causal_dual_regime |       32 | 500 |  0.064 |           24.9501 |  6.8752 |    0.1679 |    0.8625 |                0.3357 |
| plain         | adj_cusum        | single_threshold   |        5 | 500 |  0.01  |           24.9501 |  6.8752 |    1      |    0.0001 |                0.0003 |
| plain         | topk_cusum       | causal_dual_regime |       26 | 500 |  0.052 |           24.9501 |  6.8752 |    0.4424 |    0.613  |                0.8848 |
| plain         | topk_cusum       | single_threshold   |        4 | 500 |  0.008 |           24.9501 |  6.8752 |    1      |    0      |                0.0001 |
| plain         | hier_ssm         | causal_dual_regime |       15 | 500 |  0.03  |           24.9501 |  6.8752 |    0.9494 |    0.0728 |                0.1456 |
| plain         | hier_ssm         | single_threshold   |       16 | 500 |  0.032 |           24.9501 |  6.8752 |    0.9272 |    0.1008 |                0.2015 |
| step          | matched_contrast | causal_dual_regime |       19 | 500 |  0.038 |           24.9501 |  6.8752 |    0.8251 |    0.2205 |                0.4411 |
| step          | matched_contrast | single_threshold   |       46 | 500 |  0.092 |           24.9501 |  6.8752 |    0.0044 |    0.9968 |                0.0088 |
| step          | adj_cusum        | causal_dual_regime |       45 | 500 |  0.09  |           24.9501 |  6.8752 |    0.006  |    0.9956 |                0.0121 |
| step          | adj_cusum        | single_threshold   |      167 | 500 |  0.334 |           24.9501 |  6.8752 |    0      |    1      |                0      |
| step          | topk_cusum       | causal_dual_regime |       38 | 500 |  0.076 |           24.9501 |  6.8752 |    0.0438 |    0.9662 |                0.0875 |
| step          | topk_cusum       | single_threshold   |      163 | 500 |  0.326 |           24.9501 |  6.8752 |    0      |    1      |                0      |
| step          | hier_ssm         | causal_dual_regime |       34 | 500 |  0.068 |           24.9501 |  6.8752 |    0.1116 |    0.9104 |                0.2231 |
| step          | hier_ssm         | single_threshold   |       47 | 500 |  0.094 |           24.9501 |  6.8752 |    0.0032 |    0.9977 |                0.0064 |

## Selector Confusion Matrix

| dataset                 | true_regime   | selected_regime   |   count |   rate |
|:------------------------|:--------------|:------------------|--------:|-------:|
| v1_exp7_1000_eval_nulls | plain         | plain             |     500 | 1      |
| v1_exp7_1000_eval_nulls | plain         | step              |       0 | 0      |
| v1_exp7_1000_eval_nulls | step          | plain             |       1 | 0.002  |
| v1_exp7_1000_eval_nulls | step          | step              |     499 | 0.998  |
| fresh_4000_per_regime   | plain         | plain             |    3997 | 0.9992 |
| fresh_4000_per_regime   | plain         | step              |       3 | 0.0008 |
| fresh_4000_per_regime   | step          | plain             |       2 | 0.0005 |
| fresh_4000_per_regime   | step          | step              |    3998 | 0.9995 |

## Recalibrated Dual-Regime Validation (B=2000, n=2000)

| regime   | method           |   threshold |    B |   k_order |   alerts |    n |   rate |   ci_lo |   ci_hi |   expected_alerts |   bb_sd |   bb_pvalue_two_sided | pass_g2   |
|:---------|:-----------------|------------:|-----:|----------:|---------:|-----:|-------:|--------:|--------:|------------------:|--------:|----------------------:|:----------|
| plain    | matched_contrast |      1.1526 | 2000 |      1901 |       86 | 2000 | 0.043  |  0.0345 |  0.0528 |             99.95 | 13.7756 |                0.329  | True      |
| plain    | adj_cusum        |     58.1813 | 2000 |      1901 |      132 | 2000 | 0.066  |  0.0555 |  0.0778 |             99.95 | 13.7756 |                0.0299 | True      |
| plain    | topk_cusum       |    111.807  | 2000 |      1901 |      111 | 2000 | 0.0555 |  0.0459 |  0.0665 |             99.95 | 13.7756 |                0.4356 | True      |
| plain    | hier_ssm         |     -0.8332 | 2000 |      1901 |      118 | 2000 | 0.059  |  0.0491 |  0.0702 |             99.95 | 13.7756 |                0.2089 | True      |
| step     | matched_contrast |      1.2044 | 2000 |      1901 |       90 | 2000 | 0.045  |  0.0363 |  0.055  |             99.95 | 13.7756 |                0.5036 | True      |
| step     | adj_cusum        |    125.559  | 2000 |      1901 |      101 | 2000 | 0.0505 |  0.0413 |  0.061  |             99.95 | 13.7756 |                0.9422 | True      |
| step     | topk_cusum       |    241.143  | 2000 |      1901 |       82 | 2000 | 0.041  |  0.0327 |  0.0506 |             99.95 | 13.7756 |                0.197  | True      |
| step     | hier_ssm         |     -0.6722 | 2000 |      1901 |       94 | 2000 | 0.047  |  0.0381 |  0.0572 |             99.95 | 13.7756 |                0.713  | True      |

## Calibration vs Validation Maxima Exchangeability (KS / Mann-Whitney)

| regime   | method           |   cal_mean |   val_mean |   cal_q95 |   val_q95 |   ks_stat |   ks_p |   mw_p |   n_cal |   n_val |
|:---------|:-----------------|-----------:|-----------:|----------:|----------:|----------:|-------:|-------:|--------:|--------:|
| plain    | matched_contrast |     0.8398 |     0.8362 |    1.1521 |    1.1412 |    0.017  | 0.9348 | 0.5919 |    2000 |    2000 |
| plain    | adj_cusum        |    34.3662 |    35.2106 |   57.8681 |   60.9624 |    0.0325 | 0.2415 | 0.1301 |    2000 |    2000 |
| plain    | topk_cusum       |    66.7798 |    67.9385 |  111.314  |  112.921  |    0.0315 | 0.2742 | 0.1258 |    2000 |    2000 |
| plain    | hier_ssm         |    -1.8282 |    -1.8048 |   -0.8333 |   -0.7984 |    0.03   | 0.3292 | 0.2198 |    2000 |    2000 |
| step     | matched_contrast |     0.8388 |     0.8377 |    1.2038 |    1.1939 |    0.0285 | 0.3911 | 0.6948 |    2000 |    2000 |
| step     | adj_cusum        |    64.3603 |    64.8213 |  125.468  |  125.714  |    0.024  | 0.6123 | 0.5826 |    2000 |    2000 |
| step     | topk_cusum       |   121.901  |   122.845  |  241.036  |  234.592  |    0.0345 | 0.1849 | 0.4765 |    2000 |    2000 |
| step     | hier_ssm         |    -1.7105 |    -1.7579 |   -0.6725 |   -0.7029 |    0.0375 | 0.1201 | 0.0212 |    2000 |    2000 |

## Maxima Tail Diagnostics (5% Hill Window)

| regime   | method           | split   |   tail_frac |   k_order_tail |   hill_or_excess |      q50 |      q95 |      q99 |   q99_over_q95 |   skewness |   excess_kurtosis |
|:---------|:-----------------|:--------|------------:|---------------:|-----------------:|---------:|---------:|---------:|---------------:|-----------:|------------------:|
| plain    | matched_contrast | cal     |        0.05 |            100 |           0.0734 |   0.8225 |   1.1521 |   1.2889 |         1.1187 |     0.5255 |            0.243  |
| plain    | matched_contrast | val     |        0.05 |            100 |           0.0709 |   0.8187 |   1.1412 |   1.2789 |         1.1206 |     0.46   |            0.235  |
| plain    | adj_cusum        | cal     |        0.05 |            100 |           0.1637 |  32.2263 |  57.8681 |  76.3133 |         1.3187 |     1.1997 |            2.3087 |
| plain    | adj_cusum        | val     |        0.05 |            100 |           0.1598 |  32.631  |  60.9624 |  79.3884 |         1.3023 |     1.2932 |            2.3879 |
| plain    | topk_cusum       | cal     |        0.05 |            100 |           0.1288 |  63.3511 | 111.314  | 135.613  |         1.2183 |     0.9638 |            1.1071 |
| plain    | topk_cusum       | val     |        0.05 |            100 |           0.1449 |  64.1816 | 112.921  | 142.384  |         1.2609 |     1.172  |            2.1909 |
| plain    | hier_ssm         | cal     |        0.05 |            100 |           0.1703 |  -1.7725 |  -0.8333 |  -0.5491 |       nan      |    -0.5157 |            0.128  |
| plain    | hier_ssm         | val     |        0.05 |            100 |           0.1654 |  -1.7331 |  -0.7984 |  -0.5425 |       nan      |    -0.6384 |            0.6323 |
| step     | matched_contrast | cal     |        0.05 |            100 |           0.0844 |   0.8284 |   1.2038 |   1.3884 |         1.1533 |     0.2142 |            0.3289 |
| step     | matched_contrast | val     |        0.05 |            100 |           0.0823 |   0.8277 |   1.1939 |   1.3604 |         1.1394 |     0.2424 |            0.1467 |
| step     | adj_cusum        | cal     |        0.05 |            100 |           0.1711 |  58.047  | 125.468  | 164.97   |         1.3148 |     1.1105 |            1.644  |
| step     | adj_cusum        | val     |        0.05 |            100 |           0.1458 |  58.9262 | 125.714  | 157.994  |         1.2568 |     0.9359 |            0.984  |
| step     | topk_cusum       | cal     |        0.05 |            100 |           0.1393 | 110.35   | 241.036  | 308.822  |         1.2812 |     1.0308 |            1.1755 |
| step     | topk_cusum       | val     |        0.05 |            100 |           0.146  | 112.561  | 234.592  | 297.509  |         1.2682 |     0.9317 |            1.1783 |
| step     | hier_ssm         | cal     |        0.05 |            100 |           0.1246 |  -1.6373 |  -0.6725 |  -0.4815 |       nan      |    -0.899  |            1.6819 |
| step     | hier_ssm         | val     |        0.05 |            100 |           0.1932 |  -1.6824 |  -0.7029 |  -0.3977 |       nan      |    -0.6563 |            0.5798 |
