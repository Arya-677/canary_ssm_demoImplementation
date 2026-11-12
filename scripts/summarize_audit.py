"""Render null-audit CSVs as markdown. Every number comes from the CSV (handoff integrity rule).
usage: python scripts/summarize_audit.py label::path.csv [label::path.csv ...] > table.md"""
import sys
import pandas as pd

for arg in sys.argv[1:]:
    label, path = arg.split("::", 1)
    d = pd.read_csv(path)
    d["cell"] = d.apply(lambda r: f"{100*r.rate:.1f}% [{100*r.ci_lo:.1f}, {100*r.ci_hi:.1f}]" + (" ABOVE" if r.ci_lo > 0.05 else ""), axis=1)
    print(f"\n### {label}  (n={int(d['n'].iloc[0])} null rollouts per cell; ABOVE = whole 95% interval above 5%)\n")
    print(d.pivot(index="method", columns="family", values="cell").to_markdown())
