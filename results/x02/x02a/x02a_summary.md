# X-0.2(a) Diagnosis: hier_arwhite vs hier_ssm

_Generated strictly from saved CSV/JSON outputs._


## Nuisance Parameter Comparison

| world                          |   class | main_noise   | arwhite_noise   |   phi_main |   phi_arwhite |   q_main |   q_arwhite |   v_main |   v_arwhite |   abs_v_diff | boundary_hit_main   | boundary_hit_arwhite   |   best_nll_main |   best_nll_arwhite |
|:-------------------------------|--------:|:-------------|:----------------|-----------:|--------------:|---------:|------------:|---------:|------------:|-------------:|:--------------------|:-----------------------|----------------:|-------------------:|
| meas_sd=0.0 (artifacts/model)  |       0 | ar_only      | ar_white        |   0.605893 |      0.60594  | 0.019977 |    0.019977 |   0.0001 |    0.000101 |     1e-06    | False               | False                  |         -514410 |            -514410 |
| meas_sd=0.0 (artifacts/model)  |       1 | ar_only      | ar_white        |   0.605315 |      0.605319 | 0.019961 |    0.019961 |   0.0001 |    0.0001   |     0        | False               | True                   |         -506336 |            -506336 |
| meas_sd=0.01 (40 dev rollouts) |       0 | ar_only      | ar_white        |   0.522023 |      0.602974 | 0.023004 |    0.020008 |   0.0001 |    0.009918 |     0.009818 | False               | False                  |         -195781 |            -195881 |
| meas_sd=0.01 (40 dev rollouts) |       1 | ar_only      | ar_white        |   0.523414 |      0.581811 | 0.022998 |    0.020813 |   0.0001 |    0.008582 |     0.008482 | False               | False                  |         -195803 |            -195855 |

## Score Difference Summary Across 50 Rollouts

| world        |   rollouts |   max_abs_diff_median |   max_abs_diff_max |   frac_gt_1e12 |   frac_gt_1e6 |
|:-------------|-----------:|----------------------:|-------------------:|---------------:|--------------:|
| meas_sd=0.0  |         50 |              0.000312 |           0.000701 |              1 |             1 |
| meas_sd=0.01 |         50 |              0.156727 |           0.431731 |              1 |             1 |
