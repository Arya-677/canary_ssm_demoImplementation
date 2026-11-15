"""Plot physical-world calibration evidence from saved CSVs only."""
import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--directory',default='examples/world_policy')
root = Path(ap.parse_args().directory)
all_maxima = [float(r['maximum']) for r in csv.DictReader((root/'null_maxima.csv').open())]
maxima = [v for v in all_maxima if math.isfinite(v)]
rows = list(csv.DictReader((root/'false_alerts.csv').open()))
policy = json.loads((root/'policy.json').read_text())
threshold = policy['calibration']['threshold']
fig, axes = plt.subplots(2,1,figsize=(10,8),layout='constrained')
axes[0].hist(maxima,bins=35,color='#267d91')
if isinstance(threshold,(float,int)):
    axes[0].axvline(threshold,color='#a34037',label=f"Frozen threshold · k={policy['calibration']['k']}")
    axes[0].legend()
axes[0].set(xlabel='Four-minute maximum eligible log release score',ylabel='Calibration null rollouts')
axes[0].text(.02,.83,f'Finite maxima only: {len(maxima)} / {len(all_maxima)}\nNo eligible data (−∞): {len(all_maxima)-len(maxima)}; retained in calibration',transform=axes[0].transAxes,va='top')
values = [float(r['rate']) for r in rows]
lower = [v-float(r['lower_95']) for v,r in zip(values,rows)]
upper = [float(r['upper_95'])-v for v,r in zip(values,rows)]
axes[1].errorbar(range(len(rows)),values,yerr=[lower,upper],fmt='o',capsize=6,color='#267d91')
axes[1].set_xticks(range(len(rows)),[r['channel'] for r in rows])
axes[1].axhline(policy['calibration']['alpha'],ls='--',color='#a34037',label='Nominal release-only alpha')
axes[1].set(ylabel='Independent validation false-action fraction',ylim=(0,max(.08,max(values)+.02)))
axes[1].legend()
axes[1].grid(alpha=.2)
fig.suptitle('Physical resource world · all-healthy null · fixed four-minute protocol\nPointwise exact 95% intervals; no background faults or advisory producers')
fig.savefig(root/'calibration_validation.png',dpi=130)
plt.close(fig)
