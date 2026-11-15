"""Plot saved calibration maxima and validation counts; never recompute/tune policy."""
import argparse,csv,json,math
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

p=argparse.ArgumentParser();p.add_argument('--directory',default='examples/first_crossing');a=p.parse_args();root=Path(a.directory)
maxima=[float(r['maximum']) for r in csv.DictReader((root/'null_maxima.csv').open()) if math.isfinite(float(r['maximum']))]
rows=list(csv.DictReader((root/'false_alerts.csv').open()));policy=json.loads((root/'policy.json').read_text());threshold=policy['calibration']['threshold']
fig,axes=plt.subplots(2,1,figsize=(10,8),layout='constrained');axes[0].hist(maxima,bins=35,color='#267d91',alpha=.8)
if isinstance(threshold,(float,int)):axes[0].axvline(threshold,color='#a34037',label=f"Frozen order-statistic threshold (k={policy['calibration']['k']})");axes[0].legend()
axes[0].set_xlabel('Full-horizon maximum eligible log release score');axes[0].set_ylabel('Independent calibration nulls')
values=[float(r['rate']) for r in rows];lower=[v-float(r['lower_95']) for v,r in zip(values,rows)];upper=[float(r['upper_95'])-v for v,r in zip(values,rows)]
axes[1].errorbar(range(len(rows)),values,yerr=[lower,upper],fmt='o',capsize=6,color='#267d91');axes[1].set_xticks(range(len(rows)),[r['channel'] for r in rows]);axes[1].axhline(policy['calibration']['alpha'],ls='--',color='#a34037',label='Nominal release-only alpha')
axes[1].set_ylabel('Validation rollout false-action fraction');axes[1].set_ylim(bottom=0);axes[1].legend();axes[1].grid(alpha=.2)
axes[1].set_title('Pointwise exact binomial 95% intervals; combined policy is measured separately')
fig.suptitle('Conditional Gaussian policy example · not resource-world calibration');fig.savefig(root/'calibration_validation.png',dpi=130);plt.close(fig)
