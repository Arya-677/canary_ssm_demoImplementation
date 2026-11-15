# Publication Table Index
**Canary SSM V3 — Research Paper Tables**

All tables were extracted programmatically by `scripts/make_research_figures.py` from saved experiment CSV outputs. Each table is provided in three formats:
1. Comma-Separated Values (`.csv`) for programmatic consumption.
2. GitHub-Flavored Markdown (`.md`) for direct documentation reading.
3. Formatted LaTeX (`.tex`) with `booktabs` styling for direct inclusion in manuscript drafts.

---

### Table Registry

| Table Identifier | Formats Available | Caption & Description | Underlying CSV Source |
| :--- | :--- | :--- | :--- |
| **Table 1** | [`tab1_final_test_detection_plain.csv`](paper/TABLES/tab1_final_test_detection_plain.csv)<br>[`tab1_final_test_detection_plain.md`](paper/TABLES/tab1_final_test_detection_plain.md)<br>[`tab1_final_test_detection_plain.tex`](paper/TABLES/tab1_final_test_detection_plain.tex) | **Detection Performance on Held-Out Plain Test Set.** Comprehensive detection metrics (Null FAR, Miss Rate, Premature Alarms, Late Post-Recovery Alarms, Mean Capped Time, Median Delay) across 11 detector methods on 959 evaluated fleet event rollouts. | `results/plain_final/table_detection.csv`<br>`results/plain_final/table_null_rates.csv` |
| **Table 2** | [`tab2_plain_paired_differences.csv`](paper/TABLES/tab2_plain_paired_differences.csv)<br>[`tab2_plain_paired_differences.md`](paper/TABLES/tab2_plain_paired_differences.md)<br>[`tab2_plain_paired_differences.tex`](paper/TABLES/tab2_plain_paired_differences.tex) | **Paired Differences Against Proposed Model (`hier_ssm`).** Mean capped delay differences with 95% Clopper-Pearson bootstrap intervals on the unseen plain test dataset. Shows statistically significant speedups over unpooled, mean-only, and classical baselines. | `results/plain_final/table_paired_differences.csv` |
| **Table 3** | [`tab3_combined_robustness_summary.csv`](paper/TABLES/tab3_combined_robustness_summary.csv)<br>[`tab3_combined_robustness_summary.md`](paper/TABLES/tab3_combined_robustness_summary.md)<br>[`tab3_combined_robustness_summary.tex`](paper/TABLES/tab3_combined_robustness_summary.tex) | **Multi-Stressor Robustness Scenario Evaluation Summary.** Summary of null alert rates, empirical power, miss rate, and mean capped delay across five combined perturbation families (`heavytail`, `missing`, `contamination`, `labelerror`, `step`) at $m=1$. | `results/study_combined/table_scenario_summary.csv` |

---

### Reproduction Command
To regenerate all tables in CSV, Markdown, and LaTeX:
```bash
python scripts/make_research_figures.py
```
