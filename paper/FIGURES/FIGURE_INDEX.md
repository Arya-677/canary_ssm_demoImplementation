# Publication Figure Index
**Canary SSM V3 — Research Paper Visual Materials**

All figures were generated programmatically by `scripts/make_research_figures.py` using matplotlib at 300 DPI (PNG) and vector SVG. All plotted values originate directly from saved experiment CSV and JSON files.

---

### Figure Registry

| Figure Identifier | Files (PNG / SVG) | Caption & Research Interpretation | Primary Data Source | Generation Function |
| :--- | :--- | :--- | :--- | :--- |
| **Figure 1** | [`fig1_detection_delay_comparison.png`](file:///c:/afml-implementation/paper/FIGURES/fig1_detection_delay_comparison.png)<br>[`fig1_detection_delay_comparison.svg`](file:///c:/afml-implementation/paper/FIGURES/fig1_detection_delay_comparison.svg) | **Detection Latency Across Methods on Unseen Plain Test Set.** Bar chart comparing mean horizon-capped detection time and empirical miss rate on 959 held-out fleet event rollouts. `hier_ssm` achieves 15.57 min (5.11% miss) vs 18.10 min for `indep_ssm` and 33.38 min for `glr_window`. | `results/plain_final/table_detection.csv` | `plot_fig1()` |
| **Figure 2** | [`fig2_hier_vs_indep_pooling.png`](file:///c:/afml-implementation/paper/FIGURES/fig2_hier_vs_indep_pooling.png)<br>[`fig2_hier_vs_indep_pooling.svg`](file:///c:/afml-implementation/paper/FIGURES/fig2_hier_vs_indep_pooling.svg) | **Hierarchical Pooling Contrast Across Scenarios (C2 at $m=1$).** Forest plot of paired delay differences ($\text{hier\_ssm} - \text{indep\_ssm}$) with 95% bootstrap intervals across all 16 scenarios. Highlights the H1 fleet pooling advantage in `broad_fleet` ($\Delta = -5.39\text{ min}$) and `class_wide` ($\Delta = -4.82\text{ min}$) against the localized shrinkage penalty in `single_host_persistent` ($\Delta = +9.46\text{ min}$). | `results/study_inertia/table_paired_contrasts.csv` | `plot_fig2()` |
| **Figure 3** | [`fig3_calibration_validity_gate_g2.png`](file:///c:/afml-implementation/paper/FIGURES/fig3_calibration_validity_gate_g2.png)<br>[`fig3_calibration_validity_gate_g2.svg`](file:///c:/afml-implementation/paper/FIGURES/fig3_calibration_validity_gate_g2.svg) | **Gate G2 Calibration Validity Envelope.** Scatter plot of achieved false-alert rate on independent validation nulls ($n=2,000$) versus two-sided Beta-Binomial $p$-value across all 50 primary study cells. All cells reside safely inside the Gate G2 envelope ($p \ge 0.107 \gg 0.01$, $\text{FAR} \le 5.90\% \ll 7.5\%$). | `results/study_inertia/table_calibration_validity.csv` | `plot_fig3()` |
| **Figure 4** | [`fig4_combined_robustness_heavytail.png`](file:///c:/afml-implementation/paper/FIGURES/fig4_combined_robustness_heavytail.png)<br>[`fig4_combined_robustness_heavytail.svg`](file:///c:/afml-implementation/paper/FIGURES/fig4_combined_robustness_heavytail.svg) | **Detector Performance Under Heavy-Tailed Telemetry Noise ($t(3)$).** Paired bar chart of null false-alert rate and empirical detection power. `glr_window` false alerts explode to 85.7% and `adj_cusum` to 12.7%, while `hier_ssm` maintains calibrated false-alert control (6.0%) and 99.67% power. | `results/study_combined/table_scenario_summary.csv` | `plot_fig4()` |
| **Figure 5** | [`fig5_hysteresis_tradeoff.png`](file:///c:/afml-implementation/paper/FIGURES/fig5_hysteresis_tradeoff.png)<br>[`fig5_hysteresis_tradeoff.svg`](file:///c:/afml-implementation/paper/FIGURES/fig5_hysteresis_tradeoff.svg) | **Decision Hysteresis Depth Trade-Off (H3).** Dual-axis plot of false pause reduction on benign isolated spikes (`iso_spike_1host`) versus detection delay penalty on weak persistent anomalies (`weak_persistent_3host`) across confirmation depths $m \in \{1, 3, 5, 10, 15\}$. Illustrates why H3 failed preregistered criteria. | `results/study_inertia/table_scenario_summary.csv` | `plot_fig5()` |
| **Figure 6** | [`fig6_telemetry_contrast_simulation.png`](file:///c:/afml-implementation/paper/FIGURES/fig6_telemetry_contrast_simulation.png)<br>[`fig6_telemetry_contrast_simulation.svg`](file:///c:/afml-implementation/paper/FIGURES/fig6_telemetry_contrast_simulation.svg) | **Synthetic Telemetry and State-Space Estimation Dynamics.** Multi-panel time series illustrating raw canary/control latency, workload-adjusted contrast tracking the ground-truth harmful regression $a_t$, and recursive posterior harm probability $P(\text{Harm} \mid y_{1:t})$ crossing calibrated hysteresis thresholds. | `demo/data.json` | `plot_fig6()` |

---

### Verification and Reproduction Command
To regenerate all figures:
```bash
python scripts/make_research_figures.py
```
All outputs are created in both vector SVG (`.svg`) and high-resolution raster (`.png`, 300 DPI).
