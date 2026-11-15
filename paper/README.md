# Research Paper Preparation Package: Canary SSM V3
## Hierarchical, Inertia-Constrained State-Space Models for Safer Software Rollout Decisions

This directory contains the complete publication package for authoring the formal AFML research paper. All textual skeletons, empirical claims, figures, tables, and bibliographic citations are grounded strictly in the verified experimental outputs of the Canary SSM V3 research archive.

---

### Package Contents

1. [`MANUSCRIPT_SKELETON.md`](paper/MANUSCRIPT_SKELETON.md): Complete, publication-ready academic manuscript draft with structured abstract, mathematical formulations, empirical results, and discussion.
2. [`PAPER_OUTLINE.md`](paper/PAPER_OUTLINE.md): Detailed sectional outline with word counts, section objectives, and target venues.
3. [`RESULTS_EVIDENCE_MAP.md`](paper/RESULTS_EVIDENCE_MAP.md): Traceability matrix mapping every numerical claim in the paper to its underlying CSV, row, and column.
4. [`FIGURES/`](paper/FIGURES/): Publication-ready figures in both vector SVG and 300 DPI raster PNG formats, accompanied by [`FIGURE_INDEX.md`](paper/FIGURES/FIGURE_INDEX.md).
5. [`TABLES/`](paper/TABLES/): Publication tables in CSV, Markdown, and formatted LaTeX (`.tex`) formats, accompanied by [`TABLE_INDEX.md`](paper/TABLES/TABLE_INDEX.md).
6. [`REFERENCES.bib`](paper/REFERENCES.bib): Primary-source BibTeX bibliography covering all cited literature with verified DOIs.

---

### Author Guidelines & Scientific Safeguards
- **No Novel Mathematical Family:** Describe the model as a hierarchical Dynamic Linear Model / Kalman filter with finite-sample order-statistic threshold calibration.
- **No Claims of Production Readiness:** Explicitly describe the benchmark as synthetic microservice simulation.
- **Preserve Negative Findings:** H2 (two-scale inertia), H3 (hysteresis false alarm reduction), H4 (recovery delay reduction), and H5 (universal classical dominance) were not supported and must be reported transparently.
- **Cost Check Reporting:** Always report the $+9.46\text{ min}$ detection penalty in `single_host_persistent` alongside the fleet speedup finding.
