# Related-work matrix (Addendum G). ALL rows UNVERIFIED until Antigravity/author fills them from primary sources (Phase 7).
Rule: only claim a difference that a primary source supports. Columns to fill for each row: full title, authors, year, venue, DOI/URL,
exact statistical method, assumptions, sequential?, hierarchical?, latent persistence?, workload modelling?, overlap with this project.
| Item | Why relevant | Reviewer's recollection (NOT evidence) | Status |
|---|---|---|---|
| Google Canary Analysis Service (Davidovic & Beyer, ACM Queue 2018 — confirm) | real canary system | uses statistical comparison of metrics with decisions; do NOT call it memoryless threshold | UNVERIFIED |
| Kayenta (Netflix/Google, open-source docs) | production canary judge | nonparametric (Mann-Whitney-based) per-metric classification + score aggregation — confirm in docs; repo's `mw_judge` is "Kayenta-style" only | UNVERIFIED |
| Page (1954) CUSUM; Roberts (1959) EWMA | classical baselines | | UNVERIFIED |
| Lorden / Lai GLR sequential detection | `glr_window` comparator | | UNVERIFIED |
| Xie & Siegmund (2013) sparse multi-sensor change detection | `sparse_mix_glr` | | UNVERIFIED |
| Adams & MacKay (2007) BOCPD | `bocpd` | | UNVERIFIED |
| Johari et al. always-valid inference (A/B tests) | `msprt` | | UNVERIFIED |
| Hierarchical Bayesian dynamic models (West & Harrison) ; dynamic factor models (Stock & Watson) | model family of this project | | UNVERIFIED |
| Robust state-space (Student-t/Huber) | `hier_huber` ablation | | UNVERIFIED |
| Conformal / order-statistic calibration | calibration method | | UNVERIFIED |
