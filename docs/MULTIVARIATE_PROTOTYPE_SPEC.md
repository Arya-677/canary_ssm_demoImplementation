# Multivariate prototype (Phase 6) — DEFERRED. Do not start without "GO P6".
Preconditions: Phases 1–3 accepted. Required schema change (not present today): Rollout gets `y_cpu` (T,n), `err_count` (T,n) and
`request_count` already exists as exposure; Truth gets per-metric effects. Existing latency-only paths must remain bit-identical (golden hashes).
Metrics: log-latency (Gaussian on residuals), CPU (logit-transformed utilisation, Gaussian residual), error rate (Binomial(N,p) via logit-normal
approximation ONLY after an overdispersion check; beta-binomial if overdispersed). Compare: latency-only hier; independent per-metric detectors with
calibrated score aggregation (max / Fisher / Bonferroni-calibrated by order statistic on the aggregate); joint SSM. Equal tuning budgets disclosed;
joint decision calibrated on its own nulls. Cross-metric correlation ρ∈{0,0.3,0.7}. Success criterion: joint beats independent aggregation in ≥1 preregistered
scenario with Holm p<0.05 AND no loss on irrelevant-metric scenarios. Otherwise report negative.
