"""Partial-pooling audit (Addendum C3). Pure linear algebra on the hierarchical prior; no simulation, no truth.

For a class layout and local-to-group prior ratio r, with prior covariance S = ps^2 (C C' + r^2 B B') and one
observation per host with noise SD s, the one-shot posterior mean is S (S + s^2 I)^-1 y. We report, per layout:
  own_gain    : fraction of a single-host effect recovered by that host,
  leak_class  : fraction leaked to each classmate (false 'class-wide' evidence),
  group_gain  : fraction of a class-wide effect recovered.
Writes results/v3_prep/partial_pooling_audit.csv. These are properties of the MODEL PRIOR, not experimental results.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from canary_ssm.hierarchy import class_structure

LAYOUTS = {"balanced_5_5": [0] * 5 + [1] * 5, "unbalanced_8_2": [0] * 8 + [1] * 2, "unbalanced_9_1": [0] * 9 + [1],
           "all_singletons_10": list(range(10)), "label_error_flip_3": [0, 0, 0, 0, 0, 1, 1, 1, 1, 1][:7] + [0, 0, 0]}


def main(out: str = "results/v3_prep/partial_pooling_audit.csv", ps: float = 0.005, s: float = 0.02) -> pd.DataFrame:
    rows = []
    for name, lab in LAYOUTS.items():
        cls = np.array(lab); n = len(cls); C, B = class_structure(cls)
        for r in (0.25, 0.5, 1.0, 2.0, 4.0):
            S = ps ** 2 * (C @ C.T + r ** 2 * B @ B.T)
            W = S @ np.linalg.inv(S + s ** 2 * np.eye(n))
            g0 = np.flatnonzero(cls == cls[0]); m = len(g0)
            own = W[g0[0], g0[0]]; leak = float(np.mean([W[g0[1], g0[0]]])) if m > 1 else np.nan
            grp = float(W[g0][:, g0].sum(1).mean())
            rows.append({"layout": name, "n_hosts": n, "class0_size": m, "prior_h_ratio": r, "own_gain": own,
                         "leak_to_classmate": leak, "group_gain": grp, "prior_sd": ps, "obs_sd": s})
    df = pd.DataFrame(rows); Path(out).parent.mkdir(parents=True, exist_ok=True); df.to_csv(out, index=False)
    return df


if __name__ == "__main__":
    print(main().round(4).to_string(index=False))
