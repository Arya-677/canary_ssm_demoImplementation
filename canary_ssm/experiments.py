"""Experiment orchestration (handbook Sections 9-13, 16; Change Plan P0-P1).

Artifact chain (every step consumes explicit, hash-checked artifacts):
  simulate -> data/<role>/ (+ data/<role>_truth/ evaluator-only)
  fit      -> artifacts/model/{nuisance_*.json, model_config.json, dev_selection*.csv, edge_selection.csv, fit_failures.csv}
  calibrate-> artifacts/policy/{policy.json, threshold_uncertainty.csv}
  validate -> artifacts/policy/{null_validation.json, table_validation_by_family.csv, exchangeability_audit.csv, calibration_alpha_sweep.csv, gate_status.json}
  evaluate -> results/final/*
"""
from __future__ import annotations

import copy
import functools
import itertools
import json
import math
import os
import platform
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.stats import ks_2samp, mannwhitneyu

from . import decision as dec
from . import manifest as man_mod
from . import metrics as M
from . import parallel, seeds
from .baselines import DetectorOutput, config_grid, run_baseline
from .baselines_extra import PREWHITENED_BASELINES
from .oracles import ORACLE_METHODS, is_oracle_method, run_oracle
from .factor import Adjusted
from .hierarchy import EffectDetector, EffectParams, long_run_sd
from .preprocess import Nuisance, adjust_roll, fit_nuisance
from .report import calibration_gate, null_rate_table
from .schema import KAPPA, Rollout, dict_hash, dir_hash
from .simulate import SimConfig, Truth, simulate

SEED_BASE = seeds.RANGES
BASELINES = [
    "matched_contrast", "adj_ewma", "adj_cusum", "topk_cusum",
    "wmean", "ar_cusum", "glr_window", "sparse_mix_glr", "bocpd", "msprt", "mw_judge",
]
ORACLES = list(ORACLE_METHODS)
SSMS = ["pooled_ssm", "indep_ssm", "hier_ssm"]
ABLATIONS = ["hier_no_persist", "hier_rw", "hier_rank0", "hier_arwhite", "hier_white", "hier_huber", "hier_degraded"]
REUSED = ("hier_rank0", "hier_arwhite", "hier_white", "hier_huber", "hier_degraded")   # reuse hier effect params
COMBOS = {
    "combo_hier_topk": ("hier_ssm", "topk_cusum"),
    "combo_hier_m0": ("hier_ssm", "matched_contrast"),
    "combo_m0_topk": ("matched_contrast", "topk_cusum"),
}
FROZEN = {
    "matched_contrast": {"window": 1},
    "adj_ewma": {"alpha": 0.2},
    "adj_cusum": {"k": 0.25},
    "topk_cusum": {"K": 3, "k": 0.25},
    "wmean": {"w": 15, "K": 1},
    "ar_cusum": {"k": 0.25},
    "glr_window": {"W": 30, "K": 1},
    "sparse_mix_glr": {"p0": 0.3, "W": 30},
    "bocpd": {"lambda_h": 120.0},
    "msprt": {"tau": 0.5},
    "mw_judge": {"w": 15},
    **{
        f"{m}_ssm": {
            "kind": k, "rho_g": 0.95, "rho_h": 0.95, "sd_g": 0.001,
            "sd_h_ratio": 1.0, "prior_sd": 0.01, "huber_c": 0.0,
        }
        for m, k in (("pooled", "pooled"), ("indep", "indep"), ("hier", "hier"))
    },
}   # AUDIT USE ONLY, not tuned
ALPHA = 0.05
ALPHA_LIST = [0.01, 0.02, 0.05, 0.10]
DEFAULT_GRID_PATH = Path(__file__).resolve().parents[1] / "configs" / "grids_v2.yaml"
GRID_VERSION = "v2.0"


class StrictEdgeError(RuntimeError):
    """Raised when `--strict-edges` is enabled and a tuned parameter lies on a grid boundary."""


def code_version_tag() -> str:
    """Short hash of core detector/preprocess source files for safe cache invalidation."""
    pkg = Path(__file__).resolve().parent
    parts = [pkg / n for n in ("schema.py", "factor.py", "preprocess.py", "hierarchy.py", "baselines.py", "baselines_extra.py", "decision.py")]
    return dir_hash([p for p in parts if p.exists()])[:16]


# ===================================================================== config + data
def load_config(path) -> dict:
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8-sig"))
    cross = cfg.get("cross")
    if cross:                                              # e.g. {sd_host: [0.01, 0.02, 0.04]}
        keys = list(cross); fams = []
        for f in cfg["families"]:
            for vals in itertools.product(*[cross[k] for k in keys]):
                ov = {**f.get("overrides", {}), **dict(zip(keys, vals))}
                fams.append({
                    "name": f["name"] + "@" + ",".join(f"{k}={v}" for k, v in zip(keys, vals)),
                    "weight": f.get("weight", 1.0) / np.prod([len(cross[k]) for k in keys]),
                    "overrides": ov,
                })
        cfg["families"] = fams
    return cfg


def _family_for(cfg: dict, seed: int) -> dict:
    fams = cfg["families"]; w = np.array([f.get("weight", 1.0) for f in fams], float)
    return fams[int(np.random.default_rng(seed + 99).choice(len(fams), p=w / w.sum()))]


def make_sim_cfg(cfg: dict, family: dict) -> SimConfig:
    d = {**cfg.get("sim", {}), **family.get("overrides", {}), "family": family["name"]}
    return SimConfig.from_dict(d)


def _role_seed_purpose(cfg: dict, role: str) -> str:
    return cfg.get("roles", {}).get(role, {}).get("seed_purpose", role)


def _build_role_specs(cfg: dict, role: str) -> list[dict]:
    """Deterministic ordered rollout specifications for a role manifest (supports `per_family`)."""
    role_cfg = cfg["roles"][role]
    purpose = _role_seed_purpose(cfg, role)
    use_explicit_base = "seed_base" in role_cfg
    base = int(role_cfg["seed_base"]) if use_explicit_base else seeds.RANGES[purpose]
    paired = role in ("smoke", "dev", "test")
    per_family = role_cfg.get("per_family")
    specs = []
    if per_family is not None:
        pf = int(per_family)
        for fi, fam in enumerate(cfg["families"]):
            sc = make_sim_cfg(cfg, fam)
            sc_dict = asdict(sc)
            for i in range(pf):
                seed = (base + fi * seeds.FAMILY_STRIDE + i) if use_explicit_base else seeds.seed_for(purpose, i, fi)
                for harm in ([False, True] if paired else [False]):
                    rid = f"r{seed}_{'h' if harm else 'n'}"
                    specs.append({
                        "rollout_id": rid,
                        "seed": int(seed),
                        "harm": bool(harm),
                        "pair_id": int(fi * pf + i),
                        "role": role,
                        "family": fam["name"],
                        "family_idx": int(fi),
                        "sim_cfg": sc_dict,
                    })
    else:
        n = int(role_cfg["pairs"])
        for i in range(n):
            seed = base + i if use_explicit_base else seeds.seed_for(purpose, i, 0)
            fam = _family_for(cfg, seed)
            sc = make_sim_cfg(cfg, fam)
            for harm in ([False, True] if paired else [False]):
                rid = f"r{seed}_{'h' if harm else 'n'}"
                specs.append({
                    "rollout_id": rid,
                    "seed": int(seed),
                    "harm": bool(harm),
                    "pair_id": int(i),
                    "role": role,
                    "family": fam["name"],
                    "sim_cfg": asdict(sc),
                })
    specs.sort(key=lambda s: s["rollout_id"])
    return specs


def generate_role(
    cfg: dict,
    role: str,
    out_dir: Path,
    csv: bool = False,
    manifest_only: bool = False,
    compact: bool = False,
    config_path: str | None = None,
) -> dict:
    """role sizes: dev/test -> `pairs` paired null+harm; calibration/null_validation -> `pairs` or `per_family` nulls."""
    out_dir = Path(out_dir); truth_dir = out_dir.parent / (out_dir.name + "_truth")
    role_cfg = cfg["roles"][role]
    purpose = _role_seed_purpose(cfg, role)
    use_explicit_base = "seed_base" in role_cfg
    base = int(role_cfg["seed_base"]) if use_explicit_base else seeds.RANGES[purpose]
    paired = role in ("smoke", "dev", "test")
    per_family = int(role_cfg["per_family"]) if role_cfg.get("per_family") is not None else None
    n = int(role_cfg["pairs"]) if "pairs" in role_cfg else (per_family * len(cfg["families"]) if per_family is not None else 0)
    specs = _build_role_specs(cfg, role)
    n_rollouts = len(specs)
    disk_info = parallel.check_disk_budget(out_dir, n_rollouts_to_store=0 if manifest_only else n_rollouts)

    if not manifest_only:
        out_dir.mkdir(parents=True, exist_ok=True)
        for sp in specs:
            sc = SimConfig.from_dict(sp["sim_cfg"])
            roll, truth = simulate(sc, sp["seed"], sp["harm"], sp["rollout_id"], pair_id=sp["pair_id"])
            roll.meta["pair_id"] = sp["pair_id"]; roll.meta["role"] = role
            roll.save_npz(out_dir / f"{sp['rollout_id']}.npz", compact=compact)
            truth.save(truth_dir / f"{sp['rollout_id']}.npz", compact=compact)
            if csv and sp["pair_id"] < 3:
                d = out_dir / "csv" / sp["rollout_id"]; d.mkdir(parents=True, exist_ok=True)
                roll.to_telemetry().to_csv(d / "telemetry.csv", index=False)
                (d / "metadata.json").write_text(json.dumps(roll.metadata(), indent=1), encoding="utf-8")
    else:
        out_dir.mkdir(parents=True, exist_ok=True)

    fam_counts: dict[str, int] = {}
    for sp in specs:
        fam_counts[sp["family"]] = fam_counts.get(sp["family"], 0) + 1

    if per_family is not None:
        seed_ranges = [
            (
                {"purpose": f"explicit:{purpose}", "family_idx": fi, "count": per_family,
                 "min_seed": base + fi * seeds.FAMILY_STRIDE,
                 "max_seed": base + fi * seeds.FAMILY_STRIDE + max(per_family - 1, 0)}
                if use_explicit_base else seeds.range_summary(purpose, per_family, fi)
            )
            for fi in range(len(cfg["families"]))
        ]
    else:
        seed_ranges = [
            {"purpose": f"explicit:{purpose}", "count": n, "min_seed": base, "max_seed": base + max(n - 1, 0)}
            if use_explicit_base else seeds.range_summary(purpose, n, 0)
        ]

    man = {
        "role": role,
        "regime": cfg.get("regime"),
        "n_pairs": n,
        "per_family": per_family,
        "family_counts": fam_counts,
        "paired": paired,
        "seed_purpose": purpose,
        "seed_base": base,
        "seed_ranges": seed_ranges,
        "config_hash": dict_hash(cfg),
        "config": cfg,
        "config_path": config_path,
        "n_rollouts": n_rollouts,
        "manifest_only": bool(manifest_only),
        "compact": bool(compact),
        "disk_free_bytes": disk_info["disk_free_bytes"],
    }
    (out_dir / "manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
    return man


def load_role(data_dir: Path, truth: bool = True) -> list[tuple[Rollout, Truth | None]]:
    data_dir = Path(data_dir); truth_dir = data_dir.parent / (data_dir.name + "_truth")
    out = []
    for p in sorted(data_dir.glob("r*.npz")):
        out.append((Rollout.load_npz(p), Truth.load(truth_dir / p.name) if truth else None))
    if not out:
        raise FileNotFoundError(f"no rollouts in {data_dir}")
    return out


def _rollout_specs_from_dir(data_dir: Path, truth: bool = False) -> list[dict]:
    """Reconstruct exact simulation specs from `data/<role>/manifest.json` for `--generate-on-the-fly`."""
    data_dir = Path(data_dir)
    mp = data_dir / "manifest.json"
    if not mp.exists():
        raise FileNotFoundError(f"missing manifest.json in {data_dir} required for --generate-on-the-fly")
    man = json.loads(mp.read_text(encoding="utf-8"))
    if "config" not in man:
        raise ValueError(f"{mp} lacks embedded 'config'; re-simulate manifest or run from disk")
    specs = _build_role_specs(man["config"], man["role"])
    for sp in specs:
        sp["need_truth"] = bool(truth)
    return specs


# ===================================================================== cache helpers
def _nuisance_hash_map(nuis: dict[str, Nuisance]) -> str:
    return dict_hash({k: v.to_dict() for k, v in sorted(nuis.items())})[:16]


def _atomic_savez(path: Path, **arrays) -> None:
    """Write `.npz` atomically across concurrent Windows/POSIX workers without temp collisions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    tmp = path.with_name(f"{path.stem}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp.npz")
    try:
        np.savez_compressed(tmp, **arrays)
        try:
            os.replace(tmp, path)
        except PermissionError:
            # Windows blocks os.replace while another worker finishes reading/renaming the identical cache entry.
            if not path.exists():
                time.sleep(0.05)
                try:
                    os.replace(tmp, path)
                except PermissionError:
                    if not path.exists():
                        raise
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _save_adj_cache(path: Path, adj: Adjusted) -> None:
    _atomic_savez(
        path,
        r=adj.r,
        obs=adj.obs,
        elig=adj.elig,
        U=adj.U,
        lam=adj.lam,
        sigma=adj.sigma,
        rm=adj.rm,
        class_id=adj.class_id,
        t0=adj.t0,
        fallback=adj.fallback,


        f_hat=adj.f_hat,
        **(dict(ctl_r=adj.ctl_r) if adj.ctl_r is not None else {}),
        **(dict(ctl_class_id=adj.ctl_class_id) if adj.ctl_class_id is not None else {}),
    )


def _load_adj_cache(path: Path) -> Adjusted:
    z = np.load(path, allow_pickle=False)
    return Adjusted(
        r=z["r"],
        obs=z["obs"],
        elig=z["elig"],
        U=z["U"],
        lam=z["lam"],
        sigma=z["sigma"],
        rm=z["rm"],
        class_id=z["class_id"],
        t0=int(z["t0"]),
        fallback=z["fallback"],
        f_hat=z["f_hat"],
        ctl_r=z["ctl_r"] if "ctl_r" in z else None,
        ctl_class_id=z["ctl_class_id"] if "ctl_class_id" in z else None,
    )


def _save_sel_cache(path: Path, out: DetectorOutput) -> None:
    _atomic_savez(path, score=out.score, elig=out.elig, runtime_ms=np.array([out.runtime_ms]))


def _prewarm_adj_worker(task: dict) -> str:
    """Compute and cache `Adjusted` once per rollout before candidate workers read it."""
    nuis = {k: Nuisance.from_dict(v) for k, v in task["nuis"].items()}
    mods = Models(
        nuis,
        cache_dir=Path(task["cache_dir"]),
        nuis_hash=task["nuis_hash"],
        code_ver=task["code_ver"],
    )
    roll = Rollout.load_npz(Path(task["rollout_path"]))
    for key in task["keys"]:
        mods.adjusted(roll, key, {})
    return roll.rollout_id


def _load_sel_cache(path: Path, method: str, params: dict) -> DetectorOutput:
    z = np.load(path, allow_pickle=False)
    return DetectorOutput(
        method=method,
        score=z["score"],
        elig=z["elig"],
        host_score=None,
        runtime_ms=float(z["runtime_ms"][0]),
        params=params,
    )


# ===================================================================== grids & edge checks
def _default_grids_dict() -> dict:
    return {
        "version": GRID_VERSION,
        "ssm": {
            "rho": [0.9, 0.95, 0.99, 0.995, 0.999],
            "sd_g": [0.0005, 0.001, 0.002, 0.005],
            "prior_sd": [0.01, 0.02, 0.03],
            "sd_h_ratio": [1.0],
            "constrain_long_run_sd_le_kappa": True,
        },
        "hier_no_persist": {
            "rho": [0.0],
            "sd_g": [0.005, 0.01, 0.02, 0.03, 0.05],
            "prior_sd": [0.01, 0.03, 0.05],
            "sd_h_ratio": [1.0],
            "constrain_long_run_sd_le_kappa": False,
        },
        "hier_rw": {
            "rho": [0.9999],
            "sd_g": [0.0001, 0.0003, 0.001],
            "prior_sd": [0.01, 0.02, 0.03],
            "sd_h_ratio": [1.0],
            "constrain_long_run_sd_le_kappa": False,
        },
        "adj_cusum": {"k": [0.1, 0.25, 0.5, 0.75, 1.0, 1.5]},
        "adj_ewma": {"alpha": [0.02, 0.05, 0.1, 0.2, 0.35, 0.5]},
        "topk_cusum": {"K": [1, 2, 3, 5, 7, 10], "k": [0.25, 0.5, 0.75, 1.0]},
        "matched_contrast": {"window": [1, 5, 10, 15, 30]},
        "wmean": {"w": [5, 10, 15, 30, 45], "K": [1, 3, 5]},
        "ar_cusum": {"k": [0.1, 0.25, 0.5, 0.75]},
        "glr_window": {"W": [15, 30, 45, 60], "K": [1, 3, 5]},
        "sparse_mix_glr": {"p0": [0.1, 0.3, 0.5], "W": [30, 60]},
        "bocpd": {"lambda_h": [60.0, 120.0, 240.0]},
        "msprt": {"tau": [0.25, 0.5, 1.0, 2.0]},
        "mw_judge": {"w": [15, 30]},
        "localization_cutoff": {"range": [1, 10]},
    }


def load_grids(path: Path | str | None = None) -> dict:
    p = Path(path) if path is not None else DEFAULT_GRID_PATH
    if p.exists():
        return yaml.safe_load(p.read_text(encoding="utf-8-sig"))
    return _default_grids_dict()


def ssm_grid(
    kind: str,
    persistence: bool = True,
    constrain: bool | None = None,
    grids: dict | None = None,
    spec_key: str = "ssm",
) -> list[EffectParams]:
    """Declared SSM candidate grid loaded from `grids_v2.yaml` (or v1 grid if `grids is None`)."""
    if grids is None and spec_key == "ssm":
        rhos = (0.0, 0.8, 0.95, 0.99) if persistence else (0.0,)
        sds = (0.001, 0.005, 0.01)
        priors = (0.01, 0.03)
        ratios = (1.0,)
        use_constrain = True if constrain is None else bool(constrain)
    else:
        gd = load_grids() if grids is None else grids
        spec = gd.get(spec_key, gd["ssm"])
        rhos = tuple(float(x) for x in spec["rho"]) if persistence else (0.0,)
        sds = tuple(float(x) for x in spec["sd_g"])
        priors = tuple(float(x) for x in spec["prior_sd"])
        ratios = tuple(float(x) for x in spec.get("sd_h_ratio", [1.0]))
        use_constrain = (
            bool(spec.get("constrain_long_run_sd_le_kappa", spec.get("constrain", True)))
            if constrain is None else bool(constrain)
        )
    g = [
        EffectParams(kind=kind, rho_g=r, rho_h=r, sd_g=sd, sd_h_ratio=hr, prior_sd=ps)
        for r in rhos for sd in sds for hr in ratios for ps in priors
    ]
    return [p for p in g if long_run_sd(p) <= KAPPA] if use_constrain else g


def candidate_grid(method: str, grids: dict | None = None) -> list[dict]:
    """Predeclared candidate configs from `grids` YAML (falls back to `configs/grids_v2.yaml`)."""
    gd = load_grids() if grids is None else grids
    if method in BASELINES:
        if method in gd:
            spec = gd[method]
            if method == "adj_cusum":
                return [{"k": float(k)} for k in spec["k"]]
            if method == "adj_ewma":
                return [{"alpha": float(a)} for a in spec["alpha"]]
            if method == "topk_cusum":
                return [{"K": int(K), "k": float(k)} for K in spec["K"] for k in spec["k"]]
            if method == "matched_contrast":
                return [{"window": int(w)} for w in spec["window"]]
            if method == "wmean":
                return [{"w": int(w), "K": int(K)} for w in spec["w"] for K in spec["K"]]
            if method == "ar_cusum":
                return [{"k": float(k)} for k in spec["k"]]
            if method == "glr_window":
                return [{"W": int(W), "K": int(K)} for W in spec["W"] for K in spec["K"]]
            if method == "sparse_mix_glr":
                return [{"p0": float(p0), "W": int(W)} for p0 in spec["p0"] for W in spec["W"]]
            if method == "bocpd":
                return [{"lambda_h": float(lh)} for lh in spec["lambda_h"]]
            if method == "msprt":
                return [{"tau": float(tau)} for tau in spec["tau"]]
            if method == "mw_judge":
                return [{"w": int(w)} for w in spec["w"]]
        return [p for n, p in config_grid() if n == method]

    if method == "hier_no_persist":
        key = "hier_no_persist" if "hier_no_persist" in gd else "ssm_no_persist"
        return [asdict(p) for p in ssm_grid("hier", persistence=False, grids=gd, spec_key=key)]
    if method == "hier_rw":
        return [asdict(p) for p in ssm_grid("hier", persistence=True, grids=gd, spec_key="hier_rw")]

    kind = {"pooled_ssm": "pooled", "indep_ssm": "indep", "hier_ssm": "hier"}[method]
    spec_key = method if method in gd else "ssm"
    return [asdict(p) for p in ssm_grid(kind, persistence=True, grids=gd, spec_key=spec_key)]


def detect_edge_selections(
    selected: dict,
    candidate_rows: list[dict] | pd.DataFrame,
    grid_version: str = GRID_VERSION,
) -> pd.DataFrame:
    """Flag selected numeric hyperparameters lying on min/max boundary of evaluated grid (WP-B2)."""
    df = pd.DataFrame(candidate_rows)
    cols = ["method", "parameter", "selected", "grid_min", "grid_max", "at_edge", "direction", "grid_version"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    records = []
    for m, grp in df.groupby("method", sort=False):
        if m not in selected:
            continue
        sel_p = selected[m]["params"]
        cand_ps = [json.loads(s) if isinstance(s, str) else dict(s) for s in grp["params"]]
        for k, val in sel_p.items():
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                continue
            vals = sorted({float(p[k]) for p in cand_ps if k in p and isinstance(p[k], (int, float))})
            if len(vals) <= 1:
                continue
            gmin, gmax = vals[0], vals[-1]
            v = float(val)
            at_low = math.isclose(v, gmin, rel_tol=0.0, abs_tol=1e-12)
            at_high = math.isclose(v, gmax, rel_tol=0.0, abs_tol=1e-12)
            direction = "low" if at_low else ("high" if at_high else "interior")
            records.append({
                "method": m,
                "parameter": k,
                "selected": v,
                "grid_min": gmin,
                "grid_max": gmax,
                "at_edge": bool(at_low or at_high),
                "direction": direction,
                "grid_version": grid_version,
            })
    return pd.DataFrame(records, columns=cols)


def expand_grid_config(
    grids: dict,
    edge_df: pd.DataFrame,
    primary_methods: list[str] | None = None,
    expansion_step: int = 1,
) -> dict | None:
    """Create a one-step extended copy of `grids` for any primary method hitting a grid edge (WP-B2)."""
    if edge_df.empty:
        return None
    sub = edge_df[edge_df["at_edge"]]
    if primary_methods is not None:
        sub = sub[sub["method"].isin(primary_methods)]
    if sub.empty:
        return None

    new_g = copy.deepcopy(grids)
    base_ver = str(new_g.get("version", GRID_VERSION)).split("-exp")[0]
    changed = False

    for _, row in sub.iterrows():
        m = str(row["method"])
        param = str(row["parameter"])
        direction = str(row["direction"])

        if m in BASELINES:
            spec = new_g.setdefault(m, {})
            key = param
        else:
            src_key = m if m in new_g else ("hier_no_persist" if m == "hier_no_persist" else ("hier_rw" if m == "hier_rw" else "ssm"))
            if m not in new_g:
                new_g[m] = copy.deepcopy(new_g[src_key])
            spec = new_g[m]
            key = "rho" if param == "rho_g" else param

        if key not in spec:
            continue
        vals = sorted(set(spec[key]))
        if not vals:
            continue

        new_val = None
        if key == "rho":
            if direction == "high":
                new_val = round(1.0 - 0.5 * (1.0 - float(vals[-1])), 8)
            else:
                new_val = max(0.0, round(float(vals[0]) * 0.5, 8))
        elif key == "K":
            if direction == "low" and int(vals[0]) > 1:
                new_val = max(1, int(vals[0]) - 1)
            elif direction == "high" and int(vals[-1]) < 10:
                new_val = min(10, int(vals[-1]) + 2)
        elif key in ("window", "w", "W"):
            if direction == "low" and int(vals[0]) > 1:
                new_val = max(1, int(vals[0]) // 2)
            elif direction == "high" and int(vals[-1]) < 120:
                new_val = min(120, int(round(vals[-1] * 1.5)))
        elif key == "p0":
            if direction == "low":
                new_val = max(0.02, round(float(vals[0]) * 0.5, 6))
            elif direction == "high":
                new_val = min(0.95, round(float(vals[-1]) * 1.5, 6))
        elif key == "lambda_h":
            if direction == "low":
                new_val = max(15.0, round(float(vals[0]) * 0.5, 6))
            elif direction == "high":
                new_val = min(960.0, round(float(vals[-1]) * 2.0, 6))
        elif key == "tau":
            if direction == "low":
                new_val = max(0.05, round(float(vals[0]) * 0.5, 6))
            elif direction == "high":
                new_val = min(8.0, round(float(vals[-1]) * 2.0, 6))
        elif key == "alpha":
            if direction == "low":
                new_val = max(0.005, round(float(vals[0]) * 0.5, 6))
            elif direction == "high" and float(vals[-1]) < 0.9:
                new_val = min(0.9, round(float(vals[-1]) * 1.5, 6))
        else:  # geometric scale parameters: k, sd_g, prior_sd
            if direction == "low":
                new_val = round(float(vals[0]) * 0.5, 8)
            elif direction == "high":
                cand_hi = round(float(vals[-1]) * 1.5, 8)
                if key in ("sd_g", "prior_sd"):
                    cand_hi = min(cand_hi, 0.05)
                new_val = cand_hi

        if new_val is not None and all(not math.isclose(float(new_val), float(v), rel_tol=0.0, abs_tol=1e-12) for v in vals):
            spec[key] = sorted([*vals, new_val])
            changed = True

    if not changed:
        return None
    new_g["version"] = f"{base_ver}-exp{expansion_step}"
    return new_g


class Models:
    """Binds nuisance variants + selected hyperparameters; runs any method on a Rollout."""

    def __init__(
        self,
        nuis: dict[str, Nuisance],
        selected: dict | None = None,
        misclass: float = 0.2,
        cache_dir: Path | None = None,
        nuis_hash: str | None = None,
        code_ver: str | None = None,
    ):
        self.nuis = nuis
        self.selected = selected or {}
        self.misclass = misclass
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.nuis_hash = nuis_hash or _nuisance_hash_map(nuis)
        self.code_ver = code_ver or code_version_tag()

    def adjusted(self, roll: Rollout, key: str, cache: dict) -> Adjusted:
        if key not in cache:
            n_obj = self.nuis["rank0" if key == "rank0" else "main"]
            if self.cache_dir is not None:
                nh = dict_hash(n_obj.to_dict())[:16]
                cpath = self.cache_dir / "adj" / f"{nh}_{self.code_ver}" / key / f"{roll.rollout_id}.npz"
                if cpath.exists():
                    cache[key] = _load_adj_cache(cpath)
                else:
                    adj = adjust_roll(roll, n_obj)
                    _save_adj_cache(cpath, adj)
                    cache[key] = adj
            else:
                cache[key] = adjust_roll(roll, n_obj)
        return cache[key]

    def run(self, roll: Rollout, method: str, params: dict | None = None, cache: dict | None = None) -> DetectorOutput:
        cache = {} if cache is None else cache
        params = params if params is not None else self.selected[method]["params"]
        if method in BASELINES:
            adj = self.adjusted(roll, "main", cache)
            if method in PREWHITENED_BASELINES and "phi" not in params:
                n_main = self.nuis["main"]
                phi_vec = np.array([n_main.phi_e[int(g)] for g in adj.class_id], dtype=float)
                return run_baseline(method, adj, phi=phi_vec, **params)
            return run_baseline(method, adj, **params)
        key, nk, override = "main", "main", None
        if method == "hier_rank0":
            key, nk = "rank0", "rank0"
        elif method == "hier_arwhite":
            nk = "arwhite"
        elif method == "hier_white":
            nk = "white"
        elif method == "hier_huber":
            params = {**params, "huber_c": 3.0}
        elif method == "hier_degraded":
            nc = len(roll.canary_idx); cls = roll.class_id[roll.canary_idx].copy()
            rng = np.random.default_rng(int(roll.meta.get("seed", 0)) + 7)
            flip = rng.choice(nc, size=int(round(self.misclass * nc)), replace=False)
            cls[flip] = 1 - cls[flip]; override = cls
        adj = self.adjusted(roll, key, cache)
        adj = self.adjusted(roll, key, cache)
        return EffectDetector(self.nuis[nk], EffectParams(**params), name=method, class_override=override).run(adj)

    def run_oracle(self, roll: Rollout, truth: Truth, method: str, cache: dict | None = None) -> DetectorOutput:
        """Execute a clairvoyant oracle reference (`WP-E2`); NEVER called for real competitors."""
        cache = {} if cache is None else cache
        adj = self.adjusted(roll, "main", cache)
        ep = self.selected.get("indep_ssm", {}).get("params")
        return run_oracle(method, adj, truth, nuis=self.nuis["main"], effect_params=ep)


def _safe_run(models: Models, roll, method, params, cache, failures: list):
    try:
        return models.run(roll, method, params, cache)
    except (FloatingPointError, np.linalg.LinAlgError, ValueError) as e:      # failed fits are RETAINED
        failures.append({
            "rollout_id": roll.rollout_id,
            "method": method,
            "params": json.dumps(params),
            "error": f"{type(e).__name__}: {e}",
        })
        T = roll.T
        return DetectorOutput(method, np.full(T, np.nan), np.zeros(T, bool), None)


# ===================================================================== FIT (development only)
def _alarm_outcome(out: DetectorOutput, thr: float, t0: int, ev: dict) -> dict:
    return M.classify(dec.first_alarm(out.score, out.elig, thr, t0), ev, len(out.score))


def aggregate_fold_objective(per_roll: list[dict], objective: str = "mixture") -> float:
    """Compute within-fold mean capped time under `mixture` or `family_balanced` weighting (WP-B3)."""
    if not per_roll:
        return float("inf")
    if objective == "mixture":
        return float(np.mean([float(x["capped"]) for x in per_roll]))
    if objective == "family_balanced":
        by_fam: dict[str, list[float]] = {}
        for x in per_roll:
            by_fam.setdefault(str(x["family"]), []).append(float(x["capped"]))
        return float(np.mean([np.mean(vs) for vs in by_fam.values()]))
    raise ValueError(f"Unknown objective {objective!r}; expected 'mixture' or 'family_balanced'")


def _simplicity_key(params: dict) -> tuple:
    """Smaller key = simpler / more regularised candidate for the 1-SE selection rule (WP-B3)."""
    if "rho_g" in params:
        lr = long_run_sd(EffectParams(**params))
        return (lr, float(params.get("sd_g", 0.0)), float(params.get("prior_sd", 0.0)))
    if "k" in params:
        return (-float(params["k"]), float(params.get("K", 0)))
    if "alpha" in params:
        return (-float(params["alpha"]),)
    if "window" in params:
        return (-float(params["window"]),)
    if "w" in params:
        return (-float(params["w"]), float(params.get("K", 0)))
    if "W" in params and "p0" in params:
        return (float(params["p0"]), -float(params["W"]))
    if "W" in params:
        return (-float(params["W"]), float(params.get("K", 0)))
    if "lambda_h" in params:
        return (-float(params["lambda_h"]),)
    if "tau" in params:
        return (float(params["tau"]),)
    return (0.0,)


def pick_one_se_candidate(rows: list[dict]) -> dict:
    """Select simplest candidate within 1 standard error of the best K-fold objective (WP-B3)."""
    best = min(rows, key=lambda r: float(r["dev_capped_time"]))
    limit = float(best["dev_capped_time"]) + float(best.get("dev_se", 0.0))
    eligible = [
        r for r in rows
        if np.isfinite(float(r["dev_capped_time"])) and float(r["dev_capped_time"]) <= limit + 1e-12
    ]
    if not eligible:
        return best
    return min(
        eligible,
        key=lambda r: (
            _simplicity_key(json.loads(r["params"]) if isinstance(r["params"], str) else r["params"]),
            float(r["dev_capped_time"]),
            int(r["cand"]),
        ),
    )


def _eval_candidate_core(
    models: Models,
    dev: list[tuple[Rollout, Truth | None]],
    method: str,
    params: dict,
    ci: int,
    evs: dict[str, dict],
    cache_dir: Path | None,
    code_ver: str,
    mem_adj_caches: dict[str, dict] | None = None,
    k_folds: int = 5,
    objective: str = "mixture",
) -> tuple[dict, list[dict]]:
    t_start = time.time()
    failures: list[dict] = []
    cand_hash = dict_hash(params)[:16]
    nh = models.nuis_hash
    Mx, fold_n, out_h, fold_h = [], [], [], []
    for r, t in dev:
        sel_path = (
            Path(cache_dir) / "sel" / method / f"{nh}_{code_ver}_{cand_hash}" / f"{r.rollout_id}.npz"
            if cache_dir is not None else None
        )
        if sel_path is not None and sel_path.exists():
            o = _load_sel_cache(sel_path, method, params)
        else:
            rc = mem_adj_caches.setdefault(r.rollout_id, {}) if mem_adj_caches is not None else {}
            o = _safe_run(models, r, method, params, rc, failures)
            if sel_path is not None and len(failures) == 0:
                _save_sel_cache(sel_path, o)
        f_idx = int(t.pair_id % k_folds)
        if not t.harm:
            Mx.append(dec.release_max(o.score, o.elig, r.t0))
            fold_n.append(f_idx)
        else:
            out_h.append((o.score, o.elig, r.t0, t.family, t.pair_id, evs[r.rollout_id]))
            fold_h.append(f_idx)

    Mx_a, fold_n_a, fold_h_a = np.array(Mx), np.array(fold_n), np.array(fold_h)
    fold_means = []
    all_roll_capped = []
    for f in range(k_folds):
        train_nulls = Mx_a[fold_n_a != f]
        if train_nulls.size < math.ceil(1.0 / ALPHA):
            continue
        thr = dec.calibrate_threshold(train_nulls, ALPHA)["threshold"]
        f_recs = []
        for (s, e, t0, fam_name, pid, ev), fh in zip(out_h, fold_h_a):
            if fh != f or not ev["has_event"]:
                continue
            c = M.classify(dec.first_alarm(s, e, thr, t0), ev, len(s))["capped"]
            rec = {"pair_id": int(pid), "family": fam_name, "capped": float(c)}
            f_recs.append(rec)
            all_roll_capped.append(rec)
        if f_recs:
            fold_means.append(aggregate_fold_objective(f_recs, objective=objective))

    score = float(np.mean(fold_means)) if fold_means else np.inf
    se = float(np.std(fold_means, ddof=1) / np.sqrt(len(fold_means))) if len(fold_means) > 1 else 0.0
    row = {
        "method": method,
        "cand": ci,
        "params": json.dumps(params),
        "objective": objective,
        "k_folds": int(k_folds),
        "dev_capped_time": score,
        "dev_se": se,
        "seconds": round(time.time() - t_start, 2),
    }
    return row, failures


def _eval_candidate_worker(task: dict) -> tuple[dict, list[dict]]:
    """Top-level picklable worker evaluating one candidate across all dev rollouts."""
    nuis = {k: Nuisance.from_dict(v) for k, v in task["nuis"].items()}
    models = Models(
        nuis,
        misclass=task["misclass"],
        cache_dir=Path(task["cache_dir"]) if task["cache_dir"] else None,
        code_ver=task["code_ver"],
    )
    if task["dev_dir"] is not None:
        dev = load_role(Path(task["dev_dir"]), truth=True)
        if task["max_dev_pairs"] is not None:
            dev = [(r, t) for r, t in dev if t.pair_id < task["max_dev_pairs"]]
    else:
        dev = task["dev"]
    return _eval_candidate_core(
        models,
        dev,
        task["method"],
        task["params"],
        task["cand"],
        task["evs"],
        Path(task["cache_dir"]) if task["cache_dir"] else None,
        task["code_ver"],
        mem_adj_caches={},
        k_folds=int(task.get("k_folds", 5)),
        objective=str(task.get("objective", "mixture")),
    )


def select_on_dev(
    models: Models,
    dev,
    method: str,
    grid: list[dict],
    failures: list,
    log=print,
    workers: int | None = 1,
    dev_dir: Path | None = None,
    max_dev_pairs: int | None = None,
    cache_dir: Path | None = None,
    k_folds: int = 5,
    use_one_se: bool = True,
    objective: str = "mixture",
    min_dev_nulls: int = 200,
) -> tuple[dict, list]:
    """K-fold (by pair_id % K) CV selection with 1-SE regularisation rule (WP-B3)."""
    nulls = [(r, t) for r, t in dev if not t.harm]; harms = [(r, t) for r, t in dev if t.harm]
    nc = len(nulls[0][0].canary_idx)
    if len(nulls) < min_dev_nulls:
        raise ValueError(
            f"dev set has only {len(nulls)} nulls; need >= {min_dev_nulls} for K-fold selection "
            f"(thresholds too coarse). Use more dev pairs (prefer 500) or pass allow_small_dev=True for smoke tests."
        )
    min_train = min(int(sum(t.pair_id % k_folds != f for _, t in nulls)) for f in range(k_folds))
    req_train = int(np.ceil(1.0 / ALPHA))
    if min_train < req_train:
        raise ValueError(f"dev training fold has only {min_train} nulls; need >= {req_train} for alpha={ALPHA}.")

    evs = {r.rollout_id: M.event_truth(t, nc) for r, t in harms}
    use_cache = cache_dir if cache_dir is not None else models.cache_dir
    code_ver = models.code_ver
    w = parallel.resolve_workers(workers, len(grid))

    if w > 1:
        nuis_dicts = {k: v.to_dict() for k, v in models.nuis.items()}
        tasks = [{
            "nuis": nuis_dicts,
            "misclass": models.misclass,
            "dev_dir": str(dev_dir) if dev_dir is not None else None,
            "max_dev_pairs": max_dev_pairs,
            "dev": None if dev_dir is not None else dev,
            "method": method,
            "params": params,
            "cand": ci,
            "evs": evs,
            "cache_dir": str(use_cache) if use_cache is not None else None,
            "code_ver": code_ver,
            "k_folds": int(k_folds),
            "objective": objective,
        } for ci, params in enumerate(grid)]
        res = parallel.pmap(_eval_candidate_worker, tasks, workers=w, desc=f"select:{method}", log=log)
        rows = []
        for row, cand_fail in res:
            rows.append(row)
            failures.extend(cand_fail)
            log(f"  [{method}] cand {row['cand'] + 1}/{len(grid)} capped={row['dev_capped_time']:.2f} (SE={row['dev_se']:.2f})")
    else:
        rows = []
        mem_adj: dict[str, dict] = {}
        for ci, params in enumerate(grid):
            row, cand_fail = _eval_candidate_core(
                models, dev, method, params, ci, evs, use_cache, code_ver,
                mem_adj_caches=mem_adj, k_folds=k_folds, objective=objective,
            )
            rows.append(row)
            failures.extend(cand_fail)
            log(f"  [{method}] cand {ci + 1}/{len(grid)} capped={row['dev_capped_time']:.2f} (SE={row['dev_se']:.2f})")

    best_argmin = min(rows, key=lambda r: r["dev_capped_time"])
    chosen = pick_one_se_candidate(rows) if use_one_se else best_argmin
    for r in rows:
        r["is_argmin"] = bool(r["cand"] == best_argmin["cand"])
        r["is_selected"] = bool(r["cand"] == chosen["cand"])
    return json.loads(chosen["params"]), rows


def fit(
    dev_dir: Path,
    out_dir: Path,
    methods: list[str],
    log=print,
    max_dev_pairs: int | None = None,
    grid_stride: int = 1,
    beta_mode: str = "pre",
    frozen: bool = False,
    workers: int | None = 1,
    cache_dir: Path | None = None,
    noise_mode: str = "ar_only",
    factor_rank: int = 1,
    grid_path: Path | None = None,
    strict_edges: bool = False,
    k_folds: int = 5,
    use_one_se: bool = True,
    objective: str = "mixture",
    allow_small_dev: bool = False,
    auto_expand: bool = False,
    max_expansions: int = 2,
) -> dict:
    """frozen=True skips hyperparameter selection and uses FROZEN declared values (calibration AUDITS only)."""
    t0_wall = time.time()
    dev_dir = Path(dev_dir); out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    dev_man = json.loads((dev_dir / "manifest.json").read_text(encoding="utf-8")) if (dev_dir / "manifest.json").exists() else {}
    dev = load_role(dev_dir)
    if max_dev_pairs:
        dev = [(r, t) for r, t in dev if t.pair_id < max_dev_pairs]
    healthy = [r for r, t in dev if not t.harm]
    log(f"fit: {len(healthy)} healthy dev rollouts for nuisance (beta_mode={beta_mode}, frozen={frozen})")
    nuis = {"main": fit_nuisance(healthy, factor_rank, noise_mode, beta_mode)}
    if "hier_rank0" in methods:
        nuis["rank0"] = fit_nuisance(healthy, 0, noise_mode, beta_mode)
    if "hier_arwhite" in methods:
        nuis["arwhite"] = fit_nuisance(healthy, factor_rank, "ar_white", beta_mode)
    if "hier_white" in methods:
        nuis["white"] = fit_nuisance(healthy, factor_rank, "white", beta_mode)
    for k, n in nuis.items():
        n.save(out_dir / f"nuisance_{k}.json")

    models = Models(nuis, cache_dir=cache_dir)
    if cache_dir is not None and not frozen:
        adj_keys = ["main"] + (["rank0"] if "rank0" in nuis else [])
        nuis_d = {k: v.to_dict() for k, v in nuis.items()}
        prewarm_tasks = [
            {
                "rollout_path": str(dev_dir / f"{r.rollout_id}.npz"),
                "cache_dir": str(cache_dir),
                "nuis": nuis_d,
                "nuis_hash": models.nuis_hash,
                "code_ver": models.code_ver,
                "keys": adj_keys,
            }
            for r, _ in dev
            if (dev_dir / f"{r.rollout_id}.npz").exists()
        ]
        if prewarm_tasks:
            parallel.pmap(_prewarm_adj_worker, prewarm_tasks, workers=parallel.resolve_workers(workers, len(prewarm_tasks)), desc="prewarm:adj", log=log)
    grids = load_grids(grid_path)
    min_dev_nulls = 25 if allow_small_dev else 200
    grid_history = []
    failures: list[dict] = []
    selected: dict = {}
    rows: list[dict] = []

    exp_step = 0
    while True:
        failures = []
        rows = []
        selected = {}
        cur_grid_ver = str(grids.get("version", GRID_VERSION))
        cur_grid_hash = dict_hash({m: candidate_grid(m, grids)[::grid_stride] for m in methods if m not in REUSED})
        grid_snapshot_path = out_dir / f"grids_used_{cur_grid_ver}.yaml"
        grid_snapshot_path.write_text(yaml.safe_dump(grids, sort_keys=False), encoding="utf-8")

        for m in methods:
            if frozen:
                base = "hier_ssm" if m in REUSED + ("hier_no_persist", "hier_rw") else m
                selected[m] = {"params": FROZEN[base], "frozen_for_audit": True, "loc_cutoff": 3}
                continue
            if m in REUSED:
                selected[m] = {"params": selected["hier_ssm"]["params"], "reused_from": "hier_ssm"}
                continue
            cands = candidate_grid(m, grids)[::grid_stride]
            best, r_rows = select_on_dev(
                models, dev, m, cands, failures, log,
                workers=workers, dev_dir=dev_dir, max_dev_pairs=max_dev_pairs, cache_dir=cache_dir,
                k_folds=k_folds, use_one_se=use_one_se, objective=objective, min_dev_nulls=min_dev_nulls,
            )
            best_argmin = min(r_rows, key=lambda rr: rr["dev_capped_time"])
            selected[m] = {
                "params": best,
                "argmin_params": json.loads(best_argmin["params"]),
                "dev_capped_time": float(next(rr["dev_capped_time"] for rr in r_rows if rr.get("is_selected"))),
            }
            for rr in r_rows:
                rr["grid_version"] = cur_grid_ver
            rows += r_rows

        sel_df = pd.DataFrame(rows)
        sel_df.to_csv(out_dir / f"dev_selection_{cur_grid_ver}.csv", index=False)
        edge_df = detect_edge_selections(selected, rows, grid_version=cur_grid_ver) if not frozen else pd.DataFrame()
        grid_history.append({"version": cur_grid_ver, "hash": cur_grid_hash, "edges": int(edge_df["at_edge"].sum()) if not edge_df.empty else 0})

        if auto_expand and not frozen and exp_step < max_expansions:
            prim = [m for m in methods if m not in REUSED and m not in ("hier_no_persist", "hier_rw")]
            next_g = expand_grid_config(grids, edge_df, primary_methods=prim, expansion_step=exp_step + 1)
            if next_g is not None:
                exp_step += 1
                log(f"WARNING: edge selection detected under {cur_grid_ver}; expanding grid to {next_g['version']} (step {exp_step}/{max_expansions})")
                grids = next_g
                continue
        break

    models.selected = selected
    if not frozen:                      # localization cutoff chosen on development across 1..n_canary (WP-B5)
        harms = [(r, t) for r, t in dev if t.harm]; nc = len(harms[0][0].canary_idx)
        max_c = min(nc, int(grids.get("localization_cutoff", {}).get("range", [1, nc])[1]))
        for m in methods:
            f1 = {c: [] for c in range(1, max_c + 1)}
            for r, t in harms[:100]:
                ev = M.event_truth(t, nc)
                if not ev["has_event"]:
                    continue
                o = _safe_run(models, r, m, None, {}, failures)
                for c in f1:
                    loc = M.localization(o, ev, cutoff=c)
                    if loc:
                        p_, rc = loc["cut_precision"], loc["cut_recall"]
                        f1[c].append(0 if p_ + rc == 0 else 2 * p_ * rc / (p_ + rc))
            f1_means = {str(c): (float(np.mean(vs)) if vs else 0.0) for c, vs in f1.items()}
            selected[m]["loc_cutoff"] = int(max(f1, key=lambda c: f1_means[str(c)] if f1[c] else -1))
            selected[m]["loc_f1_curve"] = f1_means

    sel_csv = out_dir / "dev_selection.csv"
    pd.DataFrame(rows).to_csv(sel_csv, index=False)
    edge_csv = out_dir / "edge_selection.csv"
    if not edge_df.empty:
        edge_df.to_csv(edge_csv, index=False)
        at_edge_rows = edge_df[edge_df["at_edge"]]
        for _, er in at_edge_rows.iterrows():
            log(f"WARNING: edge selection {er['method']}.{er['parameter']}={er['selected']} (grid [{er['grid_min']}, {er['grid_max']}], {er['direction']})")
        edge_flags = at_edge_rows[["method", "parameter", "selected", "grid_min", "grid_max", "direction"]].to_dict("records")
        if strict_edges and not at_edge_rows.empty:
            raise StrictEdgeError(f"strict-edges aborted fit: {len(at_edge_rows)} edge selection(s) detected: {edge_flags}")
    else:
        pd.DataFrame(columns=["method", "parameter", "selected", "grid_min", "grid_max", "at_edge", "direction", "grid_version"]).to_csv(edge_csv, index=False)
        edge_flags = []

    pd.DataFrame(failures, columns=["rollout_id", "method", "params", "error"]).to_csv(out_dir / "fit_failures.csv", index=False)

    wall_s = round(time.time() - t0_wall, 3)
    src_grid_file = str(grid_path) if grid_path is not None else (str(DEFAULT_GRID_PATH) if DEFAULT_GRID_PATH.exists() else None)
    cfg = man_mod.build_manifest(
        out_dir=out_dir,
        selected=selected,
        kappa=KAPPA,
        alpha=ALPHA,
        methods=methods,
        frozen=frozen,
        kind="frozen" if frozen else "tuned",
        beta_mode=beta_mode,
        noise_mode=noise_mode,
        factor_rank=factor_rank,
        grid_file=src_grid_file,
        grid_version=grids.get("version", GRID_VERSION),
        grid_hash=dict_hash(grids),
        grid_history=grid_history,
        candidate_table_hash=man_mod.sha256_file(sel_csv),
        edge_flags=edge_flags,
        k_folds=k_folds,
        use_one_se=use_one_se,
        objective=objective,
        config=dev_man.get("config"),
        config_hash=dev_man.get("config_hash"),
        regime=dev_man.get("regime"),
        seed_ranges=dev_man.get("seed_ranges"),
        dev_rollouts=len(dev),
        misclass=0.2,
        fit_failures=len(failures),
        wall_times={"fit_s": wall_s},
        nuisance_files=sorted(f"nuisance_{k}.json" for k in nuis),
    )
    (out_dir / "model_config.json").write_text(json.dumps(cfg, indent=1, default=str), encoding="utf-8")
    return cfg


def load_models(
    model_dir: Path,
    cache_dir: Path | None = None,
) -> tuple[Models, dict, str]:
    model_dir = Path(model_dir)
    for need in ("model_config.json", "nuisance_main.json"):
        if not (model_dir / need).exists():
            raise FileNotFoundError(f"missing model artifact {need} in {model_dir}")
    cfg = json.loads((model_dir / "model_config.json").read_text(encoding="utf-8"))
    nuis = {p.stem.replace("nuisance_", ""): Nuisance.load(p) for p in model_dir.glob("nuisance_*.json")}
    h = dir_hash([model_dir / "model_config.json", *model_dir.glob("nuisance_*.json")])
    return Models(nuis, cfg["selected"], cfg.get("misclass", 0.2), cache_dir=cache_dir), cfg, h


# ===================================================================== CALIBRATE / VALIDATE
def combine_outputs(name: str, comps: list[DetectorOutput], ecdfs: list[np.ndarray]) -> DetectorOutput:
    """Union detector with ONE false-alert budget: map each component score to the fraction of calibration-null
    rollout maxima it exceeds, take the max over components, then calibrate that combined score like any other."""
    sc = [
        np.where(np.isfinite(o.score), np.searchsorted(e, o.score, side="right") / len(e), np.nan)
        for o, e in zip(comps, ecdfs)
    ]
    elig = np.logical_and.reduce([o.elig for o in comps])
    return DetectorOutput(name, functools.reduce(np.fmax, sc), elig, None, None, float(sum(o.runtime_ms for o in comps)))


def combos_for(methods: list[str]) -> list[str]:
    return [c for c, comp in COMBOS.items() if all(x in methods for x in comp)]


def get_policy_view(pol: dict, regime: str | None = None) -> dict:
    """Normalize Policy Schema v1 or v2 into a flat regime dict with thresholds, ecdf, advisory, etc."""
    if pol.get("schema_version") == 2 and "regimes" in pol and pol["regimes"]:
        reg = regime or pol.get("default_regime") or pol.get("regime")
        if reg is None:
            reg = next(iter(pol["regimes"]))
        if reg not in pol["regimes"]:
            raise ValueError(f"Regime {reg!r} not calibrated in policy (available: {sorted(pol['regimes'])})")
        view = dict(pol["regimes"][reg])
        view.setdefault("model_hash", pol.get("model_hash"))
        view.setdefault("schema_version", 2)
        view.setdefault("regime", reg)
        return view
    if regime is not None and pol.get("regime") is not None and pol.get("regime") != regime:
        raise ValueError(f"Policy regime mismatch: policy has {pol.get('regime')!r}, requested {regime!r}")
    return pol


def run_methods(models: Models, roll: Rollout, methods: list[str], failures: list, pol: dict | None = None) -> dict:
    cache = {}
    outs = {m: _safe_run(models, roll, m, None, cache, failures) for m in methods}
    view = get_policy_view(pol) if pol else None
    if view and view.get("ecdf"):
        for c in view.get("combos", []):
            outs[c] = combine_outputs(c, [outs[x] for x in COMBOS[c]], [np.array(view["ecdf"][x]) for x in COMBOS[c]])
    return outs


def _chunked(seq: list, chunk_size: int) -> list[list]:
    return [seq[i:i + chunk_size] for i in range(0, len(seq), max(1, chunk_size))]


def _load_or_sim_rollout(item: tuple[str | None, dict | None], truth_dir: Path | None) -> tuple[Rollout, Truth | None]:
    path_str, spec = item
    if spec is not None:
        sc = SimConfig.from_dict(spec["sim_cfg"])
        roll, truth = simulate(sc, spec["seed"], spec["harm"], spec["rollout_id"], pair_id=spec["pair_id"])
        roll.meta["pair_id"] = spec["pair_id"]
        roll.meta["role"] = spec["role"]
        return roll, (truth if spec.get("need_truth") else None)
    p = Path(path_str)
    roll = Rollout.load_npz(p)
    tr = Truth.load(truth_dir / p.name) if truth_dir is not None else None
    return roll, tr


def _eval_all_methods(models: Models, r: Rollout, t: Truth | None, real_m: list[str], ora_m: list[str], failures: list, pol: dict | None) -> dict:
    outs = run_methods(models, r, real_m, failures, pol) if real_m else {}
    if ora_m:
        if t is None:
            raise ValueError(f"Oracle scoring {ora_m} requires truth metadata")
        o_cache = {}
        for om in ora_m:
            outs[om] = models.run_oracle(r, t, om, cache=o_cache)
    return outs


def _score_rollouts_chunk(task: dict) -> dict:
    """Top-level worker scoring a chunk of disk paths or on-the-fly specs."""
    model_dir = Path(task["model_dir"])
    cache_dir = Path(task["cache_dir"]) if task.get("cache_dir") else None
    models, cfg, _ = load_models(model_dir, cache_dir=cache_dir)
    pol = task.get("pol")
    pview = get_policy_view(pol) if pol else None
    methods = task["methods"]
    truth_dir = Path(task["truth_dir"]) if task.get("truth_dir") else None
    mode = task["mode"]
    regime_label = task.get("regime")
    real_m = [m for m in methods if not is_oracle_method(m)]
    ora_m = [m for m in methods if is_oracle_method(m)]
    failures: list[dict] = []

    if mode == "null_scores":
        res: list[dict] = []
        for item in task["items"]:
            r, t = _load_or_sim_rollout(item, truth_dir if ora_m else None)
            outs = _eval_all_methods(models, r, t, real_m, ora_m, failures, pol)
            rec = {
                "rollout_id": r.rollout_id,
                "t0": r.t0,
                "family": r.meta.get("family"),
                "outs": {m: (o.score, o.elig, float(o.runtime_ms)) for m, o in outs.items()},
            }
            res.append(rec)
        return {"chunk_idx": task["chunk_idx"], "items": res, "failures": failures}

    if mode == "null_maxima":
        res_mx: list[dict] = []
        for item in task["items"]:
            r, t = _load_or_sim_rollout(item, truth_dir if ora_m else None)
            outs = _eval_all_methods(models, r, t, real_m, ora_m, failures, pol)
            res_mx.append({
                "rollout_id": r.rollout_id,
                "t0": r.t0,
                "family": r.meta.get("family"),
                "maxima": {m: float(dec.release_max(o.score, o.elig, r.t0)) for m, o in outs.items()},
            })
        return {"chunk_idx": task["chunk_idx"], "items": res_mx, "failures": failures}

    if mode == "evaluate":
        rows, hostrows, flick, rt, calib_rows = [], [], [], [], []
        for item in task["items"]:
            r, t = _load_or_sim_rollout(item, truth_dir)
            nc = len(r.canary_idx)
            ev = M.event_truth(t, nc)
            for m, o in _eval_all_methods(models, r, t, real_m, ora_m, failures, pol).items():
                thr = pview["thresholds"][m]["threshold"]
                ta = dec.first_alarm(o.score, o.elig, thr, r.t0)
                c = M.classify(ta, ev, r.T)
                rows.append({
                    "rollout_id": r.rollout_id, "pair_id": t.pair_id, "family": t.family,
                    "regime": regime_label, "harm": t.harm,
                    "method": m, "kind": c["kind"], "status": c["status"], "alarm_time": ta, "onset": ev["onset"],
                    "delay": c["delay"], "capped": c["capped"], "followup": c.get("followup", np.nan),
                    "brier": M.brier(o, ev, r.t0), "elig_frac": float(o.elig[r.t0:].mean()),
                })
                loc = M.localization(o, ev, cutoff=cfg["selected"].get(m, {}).get("loc_cutoff", 3))
                if loc:
                    hostrows.append({
                        "rollout_id": r.rollout_id, "method": m, "family": t.family, **loc,
                        "host_auc": M.host_auc(o, ev),
                        "detected": c["status"] == "success",
                    })
                a = pview["advisory"][m]
                ad = dec.advisory_replay(o.score, o.elig, r.t0, a["h_on"], a["h_off"], a["n_clear"])
                flick.append({
                    "rollout_id": r.rollout_id, "method": m, "harm": t.harm, "reversals": ad["reversals"],
                    "time_paused": ad["time_paused"], "first_pause": ad["first_pause"],
                })
                rt.append({"rollout_id": r.rollout_id, "method": m, "runtime_ms_per_update": o.runtime_ms})
                if o.host_prob is not None:
                    P = o.host_prob[r.t0:][o.elig[r.t0:]]; J = ev["J"][r.t0:][o.elig[r.t0:]]
                    b = np.minimum((P * 10).astype(int), 9)
                    for k in range(10):
                        cnt = int((b == k).sum())
                        sp = float(P[b == k].sum())
                        sj = float(J[b == k].sum())
                        calib_rows.append({"rollout_id": r.rollout_id, "method": m, "bin": k, "n": cnt, "sum_p": sp, "sum_j": sj})
        return {
            "chunk_idx": task["chunk_idx"],
            "rows": rows,
            "hostrows": hostrows,
            "flick": flick,
            "rt": rt,
            "calib": calib_rows,
            "failures": failures,
        }
    raise ValueError(f"unknown chunk mode {mode!r}")


def _run_chunked_with_resume(
    tasks: list[dict],
    workers: int | None,
    resume_dir: Path | None,
    journal_name: str,
    desc: str,
    log=print,
) -> list[dict]:
    """Execute `_score_rollouts_chunk` across chunks with deterministic order and optional JSONL resume."""
    import pickle
    if resume_dir is None:
        return parallel.pmap(_score_rollouts_chunk, tasks, workers=workers, desc=desc, log=log)

    resume_dir = Path(resume_dir)
    ckpt_dir = resume_dir / f".resume_{journal_name}"
    journal = parallel.ProgressJournal(resume_dir / f"journal_{journal_name}.jsonl")
    done_keys = journal.completed_keys("chunk_idx")
    cached: dict[int, dict] = {}
    todo: list[dict] = []
    for t in tasks:
        ci = int(t["chunk_idx"])
        cp = ckpt_dir / f"chunk_{ci:05d}.pkl"
        if str(ci) in done_keys and cp.exists():
            with cp.open("rb") as f:
                cached[ci] = pickle.load(f)
        else:
            todo.append(t)

    if todo:
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        w_eff = parallel.resolve_workers(workers, len(todo))
        wave_size = max(1, w_eff * 4)
        for start in range(0, len(todo), wave_size):
            batch = todo[start:start + wave_size]
            res_new = parallel.pmap(_score_rollouts_chunk, batch, workers=workers, desc=desc, log=log)
            for out in res_new:
                ci = int(out["chunk_idx"])
                tmp = ckpt_dir / f"chunk_{ci:05d}.tmp.pkl"
                cp = ckpt_dir / f"chunk_{ci:05d}.pkl"
                with tmp.open("wb") as f:
                    pickle.dump(out, f)
                os.replace(tmp, cp)
                journal.append({"chunk_idx": ci, "failures": len(out["failures"]), "ts": time.time()})
                cached[ci] = out
    return [cached[int(t["chunk_idx"])] for t in tasks]


def _prepare_rollout_items(data_dir: Path, truth: bool, generate_on_the_fly: bool) -> tuple[list[tuple[str | None, dict | None]], list[str]]:
    data_dir = Path(data_dir)
    if generate_on_the_fly:
        specs = _rollout_specs_from_dir(data_dir, truth=truth)
        items = [(None, sp) for sp in specs]
        ids = [sp["rollout_id"] for sp in specs]
        return items, ids
    paths = sorted(data_dir.glob("r*.npz"))
    if not paths:
        raise FileNotFoundError(f"no rollouts in {data_dir}")
    return [(str(p), None) for p in paths], [p.stem for p in paths]


def _null_scores(
    models: Models,
    rolls,
    methods: list[str],
    failures: list,
    pol: dict | None = None,
) -> dict[str, list[DetectorOutput]]:
    real_m = [m for m in methods if not is_oracle_method(m)]
    ora_m = [m for m in methods if is_oracle_method(m)]
    res: dict[str, list[DetectorOutput]] = {}
    for r, t in rolls:
        for m, o in _eval_all_methods(models, r, t, real_m, ora_m, failures, pol).items():
            res.setdefault(m, []).append(o)
    return res


def calibrate(
    cal_dir: Path,
    model_dir: Path,
    out_dir: Path,
    log=print,
    workers: int | None = 1,
    cache_dir: Path | None = None,
    resume: bool = False,
    generate_on_the_fly: bool = False,
    regime: str | None = None,
    allow_regime_mismatch: bool = False,
    horizons: tuple[int, ...] = (30, 60, 120),
    include_oracles: bool = False,
) -> dict:
    t0_wall = time.time()
    cal_dir = Path(cal_dir); out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    models, cfg, mh = load_models(model_dir, cache_dir=cache_dir)
    cal_man = json.loads((cal_dir / "manifest.json").read_text(encoding="utf-8")) if (cal_dir / "manifest.json").exists() else {}
    man_regime = cal_man.get("regime")
    if regime is not None and man_regime is not None and regime != man_regime and not allow_regime_mismatch:
        raise ValueError(f"Calibration data regime={man_regime!r} disagrees with requested regime={regime!r}")
    use_regime = regime or man_regime or "plain"

    cal_methods = list(cfg["methods"]) + (list(ORACLES) if include_oracles else [])
    items, rids = _prepare_rollout_items(cal_dir, truth=include_oracles, generate_on_the_fly=generate_on_the_fly)
    cal_truth_dir = None if (generate_on_the_fly or not include_oracles) else (cal_dir.parent / (cal_dir.name + "_truth"))
    failures: list[dict] = []

    w = parallel.resolve_workers(workers, len(items))
    if w > 1 or resume or generate_on_the_fly:
        chunks = _chunked(items, max(10, min(100, len(items) // max(1, w) or 1)))
        tasks = [{
            "mode": "null_scores",
            "chunk_idx": ci,
            "items": ch,
            "model_dir": str(model_dir),
            "cache_dir": str(cache_dir) if cache_dir is not None else None,
            "methods": cal_methods,
            "pol": None,
            "truth_dir": str(cal_truth_dir) if cal_truth_dir is not None else None,
        } for ci, ch in enumerate(chunks)]
        chunk_outs = _run_chunked_with_resume(
            tasks, workers=w, resume_dir=out_dir if resume else None, journal_name="calibrate", desc="calibrate", log=log
        )
        scored_recs = []
        for co in chunk_outs:
            scored_recs.extend(co["items"])
            failures.extend(co["failures"])
        scored_recs.sort(key=lambda d: d["rollout_id"])
        t0 = scored_recs[0]["t0"]
        t0s = [rec["t0"] for rec in scored_recs]
        outs = {
            m: [
                DetectorOutput(m, rec["outs"][m][0], rec["outs"][m][1], None, runtime_ms=rec["outs"][m][2])
                for rec in scored_recs
            ]
            for m in cal_methods
        }
    else:
        rolls = load_role(cal_dir, truth=include_oracles)
        outs = _null_scores(models, rolls, cal_methods, failures)
        t0 = rolls[0][0].t0
        t0s = [r.t0 for r, _ in rolls]

    reg_block = {
        "regime": use_regime,
        "calib_hash": dict_hash({"ids": rids}),
        "alpha": cfg["alpha"],
        "alpha_list": list(ALPHA_LIST),
        "horizons": [int(h) for h in horizons],
        "B": len(rids),
        "n_calibration": len(rids),
        "seed_ranges": cal_man.get("seed_ranges"),
        "thresholds": {},
        "thresholds_by_alpha": {},
        "thresholds_by_horizon": {str(int(h)): {} for h in horizons},
        "threshold_uncertainty": {},
        "advisory": {},
        "ecdf": {},
        "maxima": {},
        "combos": [],
        "oracle_methods": [m for m in cal_methods if is_oracle_method(m)],
        "fit_failures_calibration": len(failures),
        "wall_time_s": 0.0,
    }
    unc_rows = []

    def one(m, olist):
        mx = np.array([dec.release_max(o.score, o.elig, rt0) for o, rt0 in zip(olist, t0s)])
        c = dec.calibrate_threshold(mx, cfg["alpha"]); c["insample_alert_rate"] = float(np.mean(mx > c["threshold"]))
        reg_block["thresholds"][m] = c
        reg_block["thresholds_by_alpha"][m] = dec.thresholds_for_alpha(mx, tuple(ALPHA_LIST))
        unc = dec.threshold_uncertainty(mx, alpha=cfg["alpha"], seed=0)
        reg_block["threshold_uncertainty"][m] = unc
        unc_rows.append({
            "method": m,
            "regime": use_regime,
            "alpha": unc["alpha"],
            "threshold": unc["threshold"],
            "boot_lo": unc["boot_lo"],
            "boot_hi": unc["boot_hi"],
            "far_beta_lo": unc["far_beta_lo"],
            "far_beta_hi": unc["far_beta_hi"],
        })
        for h in horizons:
            mx_h = np.array([dec.release_max(o.score, o.elig, rt0, horizon=int(h)) for o, rt0 in zip(olist, t0s)])
            reg_block["thresholds_by_horizon"][str(int(h))][m] = dec.calibrate_threshold(mx_h, cfg["alpha"])
        reg_block["advisory"][m] = dec.calibrate_advisory([o.score for o in olist], [o.elig for o in olist], t0, cfg["alpha"])
        log(f"  [{use_regime}] {m:18s} thr={c['threshold']:.4g} (k={c['k']}/{c['B']})")
        return mx

    for m in cal_methods:
        mx = one(m, outs[m])
        s_mx = sorted(float(v) if np.isfinite(v) else -1e18 for v in mx)
        reg_block["ecdf"][m] = s_mx
        reg_block["maxima"][m] = s_mx
    for c in combos_for(cal_methods):
        comb = [
            combine_outputs(c, [outs[x][i] for x in COMBOS[c]], [np.array(reg_block["ecdf"][x]) for x in COMBOS[c]])
            for i in range(len(rids))
        ]
        mx_c = one(c, comb); reg_block["combos"].append(c)
        s_mx = sorted(float(v) if np.isfinite(v) else -1e18 for v in mx_c)
        reg_block["ecdf"][c] = s_mx
        reg_block["maxima"][c] = s_mx

    wall_s = round(time.time() - t0_wall, 3)
    reg_block["wall_time_s"] = wall_s

    pol = {
        "schema_version": 2,
        "model_hash": mh,
        "default_regime": use_regime,
        "regime": use_regime,
        "regimes": {use_regime: reg_block},
        # Flat mirrors for v1 reader compatibility:
        **{
            k: reg_block[k]
            for k in (
                "calib_hash", "alpha", "alpha_list", "horizons", "B", "n_calibration", "seed_ranges",
                "thresholds", "thresholds_by_alpha", "thresholds_by_horizon", "threshold_uncertainty",
                "advisory", "ecdf", "combos", "fit_failures_calibration", "wall_time_s",
            )
        },
    }
    (out_dir / "policy.json").write_text(json.dumps(pol, indent=1), encoding="utf-8")
    pd.DataFrame(unc_rows).to_csv(out_dir / "threshold_uncertainty.csv", index=False)
    return pol


def load_policy(policy_dir: Path, model_hash: str) -> dict:
    p = Path(policy_dir) / "policy.json"
    if not p.exists():
        raise FileNotFoundError(f"missing policy artifact {p}")
    pol = json.loads(p.read_text(encoding="utf-8"))
    if pol["model_hash"] != model_hash:
        raise ValueError("policy was calibrated for a different model artifact (hash mismatch)")
    return pol


def _rec_release_max(rec: dict, method: str) -> float:
    if "maxima" in rec:
        return float(rec["maxima"][method])
    return dec.release_max(rec["outs"][method][0], rec["outs"][method][1], rec["t0"])


def _rec_alerted(rec: dict, method: str, thr: float) -> bool:
    if "maxima" in rec:
        return float(rec["maxima"][method]) > float(thr)
    return dec.first_alarm(rec["outs"][method][0], rec["outs"][method][1], thr, rec["t0"]) is not None


def _alert_table_from_recs(recs: list[dict], methods_all: list[str], pview: dict) -> dict:
    rep = {}
    fam = [rec["family"] for rec in recs]
    for m in methods_all:
        thr = pview["thresholds"][m]["threshold"]
        al = np.array([_rec_alerted(rec, m, thr) for rec in recs])
        k, n = int(al.sum()), len(al); lo, hi = M.clopper_pearson(k, n)
        cinfo = pview["thresholds"][m]
        bb = M.betabinom_for_threshold(k, n, int(cinfo["B"]), int(cinfo["k"]))
        rep[m] = {
            "alerts": k, "n": n, "rate": k / n, "ci95": [lo, hi], "target": pview["alpha"],
            "expected_alerts": bb["expected_alerts"], "bb_sd": bb["bb_sd"],
            "bb_pvalue_two_sided": bb["bb_pvalue_two_sided"],
            "pass_contains_5pct": bool(lo <= pview["alpha"] <= hi), "pass_upper_le_8pct": bool(hi <= 0.08),
            "by_family": {f: float(al[[x == f for x in fam]].mean()) for f in sorted(set(fam))},
        }
    return rep


def validate_null(
    val_dir: Path,
    model_dir: Path,
    policy_dir: Path,
    log=print,
    workers: int | None = 1,
    cache_dir: Path | None = None,
    resume: bool = False,
    generate_on_the_fly: bool = False,
    allow_regime_mismatch: bool = False,
    min_n_gate: int = 2000,
    include_oracles: bool | None = None,
) -> dict:
    val_dir = Path(val_dir); policy_dir = Path(policy_dir)
    models, cfg, mh = load_models(model_dir, cache_dir=cache_dir)
    pol = load_policy(policy_dir, mh)
    val_man = json.loads((val_dir / "manifest.json").read_text(encoding="utf-8")) if (val_dir / "manifest.json").exists() else {}
    val_regime = val_man.get("regime")
    pol_regime = pol.get("default_regime") or pol.get("regime")
    if val_regime is not None and pol_regime is not None and val_regime != pol_regime and not allow_regime_mismatch:
        raise ValueError(
            f"Regime mismatch in validate_null: policy regime={pol_regime!r} vs data regime={val_regime!r}. "
            "Pass allow_regime_mismatch=True / --allow-regime-mismatch only for explicit audits."
        )
    pview = get_policy_view(pol, regime=None if allow_regime_mismatch else val_regime)

    use_ora = any(is_oracle_method(m) for m in pview["thresholds"]) if include_oracles is None else bool(include_oracles)
    val_methods = list(cfg["methods"]) + (list(ORACLES) if use_ora else [])
    val_truth_dir = None if (generate_on_the_fly or not use_ora) else (val_dir.parent / (val_dir.name + "_truth"))
    items, _ = _prepare_rollout_items(val_dir, truth=use_ora, generate_on_the_fly=generate_on_the_fly)
    failures: list[dict] = []

    w = parallel.resolve_workers(workers, len(items))
    if w > 1 or resume or generate_on_the_fly:
        chunks = _chunked(items, max(10, min(100, len(items) // max(1, w) or 1)))
        tasks = [{
            "mode": "null_maxima",
            "chunk_idx": ci,
            "items": ch,
            "model_dir": str(model_dir),
            "cache_dir": str(cache_dir) if cache_dir is not None else None,
            "methods": val_methods,
            "pol": pol,
            "truth_dir": str(val_truth_dir) if val_truth_dir is not None else None,
        } for ci, ch in enumerate(chunks)]
        chunk_outs = _run_chunked_with_resume(
            tasks, workers=w, resume_dir=policy_dir if resume else None, journal_name="validate_null", desc="validate-null", log=log
        )
        scored_recs = []
        for co in chunk_outs:
            scored_recs.extend(co["items"])
            failures.extend(co["failures"])
        scored_recs.sort(key=lambda d: d["rollout_id"])
    else:
        rolls = load_role(val_dir, truth=use_ora)
        real_v = [m for m in val_methods if not is_oracle_method(m)]
        ora_v = [m for m in val_methods if is_oracle_method(m)]
        scored_recs = []
        for r, t in rolls:
            outs = _eval_all_methods(models, r, t, real_v, ora_v, failures, pol)
            scored_recs.append({
                "rollout_id": r.rollout_id,
                "t0": r.t0,
                "family": r.meta.get("family"),
                "maxima": {m: float(dec.release_max(o.score, o.elig, r.t0)) for m, o in outs.items()},
            })
        scored_recs.sort(key=lambda d: d["rollout_id"])

    methods_all = list(val_methods) + list(pview.get("combos", []))
    rep = _alert_table_from_recs(scored_recs, methods_all, pview)

    # Build per-rollout null alert & maxima tables for Gate G2, Exchangeability Audit, Alpha Sweep
    per_roll_rows = []
    val_maxima: dict[str, np.ndarray] = {}
    alpha_sweep_rows = []
    exch_rows = []
    for m in methods_all:
        thr = pview["thresholds"][m]["threshold"]
        mx_v = np.array([_rec_release_max(rec, m) for rec in scored_recs], float)
        val_maxima[m] = mx_v
        for rec in scored_recs:
            al = _rec_alerted(rec, m, thr)
            per_roll_rows.append({"family": rec["family"] or "unknown", "method": m, "alerted": bool(al)})

        # Exchangeability audit vs stored calibration maxima
        cal_mx = np.asarray(pview.get("maxima", pview.get("ecdf", {})).get(m, []), float)
        if cal_mx.size > 0 and mx_v.size > 0:
            ks_s, ks_p = ks_2samp(cal_mx, mx_v)
            mw_s, mw_p = mannwhitneyu(cal_mx, mx_v, alternative="two-sided")
            exch_rows.append({
                "method": m, "regime": pol_regime,
                "ks_stat": float(ks_s), "ks_p": float(ks_p), "mw_p": float(mw_p),
                "n_cal": int(len(cal_mx)), "n_val": int(len(mx_v)),
            })

        # Multi-alpha sweep
        t_by_a = pview.get("thresholds_by_alpha", {}).get(m, {})
        for a_val in ALPHA_LIST:
            a_info = t_by_a.get(str(a_val)) or dec.calibrate_threshold(cal_mx, a_val) if cal_mx.size else None
            if a_info is None:
                continue
            k_a = int(np.sum(mx_v > float(a_info["threshold"])))
            n_v = len(mx_v)
            lo_a, hi_a = M.clopper_pearson(k_a, n_v)
            bb_a = M.betabinom_for_threshold(k_a, n_v, int(a_info["B"]), int(a_info["k"]))
            alpha_sweep_rows.append({
                "method": m, "regime": pol_regime, "alpha": float(a_val),
                "k": int(a_info["k"]), "B": int(a_info["B"]), "threshold": float(a_info["threshold"]),
                "n_val": n_v, "alerts": k_a, "achieved_rate_validation": k_a / n_v,
                "ci_lo": lo_a, "ci_hi": hi_a, "bb_pvalue_two_sided": bb_a["bb_pvalue_two_sided"],
            })

    nl_df = pd.DataFrame(per_roll_rows)
    fam_tbl = null_rate_table(nl_df, ["family", "method"], cal_info=pview["thresholds"], min_n=min_n_gate)
    fam_tbl.insert(2, "regime", pol_regime)
    fam_tbl["n"] = fam_tbl["n_null"]
    fam_tbl.to_csv(policy_dir / "table_validation_by_family.csv", index=False)
    pd.DataFrame(exch_rows).to_csv(policy_dir / "exchangeability_audit.csv", index=False)
    pd.DataFrame(alpha_sweep_rows).to_csv(policy_dir / "calibration_alpha_sweep.csv", index=False)
    gate = calibration_gate(fam_tbl, gate_mode="g2", min_n=min_n_gate, regime=pol_regime)
    (policy_dir / "gate_status.json").write_text(json.dumps(gate, indent=1), encoding="utf-8")

    for m, v in rep.items():
        log(f"  {m:18s} {v['alerts']}/{v['n']} = {v['rate']:.3f}  CI [{v['ci95'][0]:.3f},{v['ci95'][1]:.3f}]  "
            f"bb_p={v['bb_pvalue_two_sided']:.4f}")
    (policy_dir / "null_validation.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    return rep


def audit_null(
    cfg_path: Path,
    model_dir: Path,
    policy_dir: Path,
    n: int = 500,
    out_dir: Path = Path("results/audit"),
    methods: list[str] | None = None,
    seed_base: int | None = None,
    seed_purpose: str = "audit",
    workers: int | None = 1,
    cache_dir: Path | None = None,
    log=print,
) -> pd.DataFrame:
    """Fresh NULL rollouts for every family in cfg scored with the FROZEN model + policy."""
    cfg = load_config(cfg_path); _, mcfg, mh = load_models(model_dir); pol = load_policy(policy_dir, mh)
    pview = get_policy_view(pol)
    meths = [m for m in (methods or mcfg["methods"]) if m in mcfg["methods"]]
    rows = []
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    for fi, fam in enumerate(cfg["families"]):
        sc = make_sim_cfg(cfg, fam)
        sc_dict = asdict(sc)
        items: list[tuple[str | None, dict | None]] = []
        for i in range(n):
            seed = (seed_base + fi * 100_000 + i) if seed_base is not None else seeds.seed_for(seed_purpose, i, fi)
            items.append((None, {
                "rollout_id": f"a{seed}",
                "seed": int(seed),
                "harm": False,
                "pair_id": int(i),
                "role": seed_purpose,
                "family": fam["name"],
                "sim_cfg": sc_dict,
                "need_truth": False,
            }))
        w = parallel.resolve_workers(workers, len(items))
        chunks = _chunked(items, max(10, min(100, len(items) // max(1, w) or 1)))
        tasks = [{
            "mode": "null_scores",
            "chunk_idx": ci,
            "items": ch,
            "model_dir": str(model_dir),
            "cache_dir": str(cache_dir) if cache_dir is not None else None,
            "methods": meths,
            "pol": pol,
            "truth_dir": None,
        } for ci, ch in enumerate(chunks)]
        chunk_outs = _run_chunked_with_resume(tasks, workers=w, resume_dir=None, journal_name="audit", desc=f"audit:{fam['name']}", log=log)
        recs, failures = [], []
        for co in chunk_outs:
            recs.extend(co["items"])
            failures.extend(co["failures"])
        recs.sort(key=lambda d: d["rollout_id"])
        t0 = sc.t_pre
        methods_out = list(recs[0]["outs"].keys()) if recs else meths
        for m in methods_out:
            thr = pview["thresholds"][m]["threshold"]
            cinfo = pview["thresholds"][m]
            k = sum(dec.first_alarm(rec["outs"][m][0], rec["outs"][m][1], thr, t0) is not None for rec in recs)
            lo, hi = M.clopper_pearson(k, n)
            bb = M.betabinom_for_threshold(k, n, int(cinfo["B"]), int(cinfo["k"]))
            rows.append({
                "family": fam["name"], "method": m, "alerts": k, "n": n, "rate": k / n, "ci_lo": lo, "ci_hi": hi,
                "expected_alerts": bb["expected_alerts"], "bb_pvalue_two_sided": bb["bb_pvalue_two_sided"],
                "pass_contains_5pct": bool(lo <= pview["alpha"] <= hi), "pass_upper_le_8pct": bool(hi <= 0.08),
                "above_target": bool(lo > pview["alpha"]), "gate_evaluable": bool(n >= 400),
                "abstain_frac": float(np.mean([1 - rec["outs"][m][1][t0:].mean() for rec in recs])),
                "fit_failures": len(failures),
            })
        log(f"  family {fam['name']}: done")
    df = pd.DataFrame(rows).sort_values(["family", "method"]).reset_index(drop=True)
    df.to_csv(out_dir / "table_audit_null.csv", index=False)
    return df


# ===================================================================== EVALUATE
def evaluate(
    test_dir: Path,
    model_dir: Path,
    policy_dir: Path,
    out_dir: Path,
    log=print,
    workers: int | None = 1,
    cache_dir: Path | None = None,
    resume: bool = False,
    generate_on_the_fly: bool = False,
    allow_frozen: bool = False,
    allow_regime_mismatch: bool = False,
    include_oracles: bool | None = None,
) -> Path:
    t0_wall = time.time()
    test_dir = Path(test_dir); out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    _, cfg, mh = load_models(model_dir, cache_dir=cache_dir)
    if (cfg.get("kind") == "frozen" or cfg.get("frozen")) and not allow_frozen:
        raise ValueError(
            "Refusing frozen audit model in evaluate() (WP-B6). Pass allow_frozen=True / --allow-frozen for explicit audit runs only."
        )
    pol = load_policy(policy_dir, mh)
    test_man = json.loads((test_dir / "manifest.json").read_text(encoding="utf-8")) if (test_dir / "manifest.json").exists() else {}
    test_regime = test_man.get("regime")
    pol_regime = pol.get("default_regime") or pol.get("regime")
    if test_regime is not None and pol_regime is not None and test_regime != pol_regime and not allow_regime_mismatch:
        raise ValueError(
            f"Regime mismatch in evaluate(): policy regime={pol_regime!r} vs test data regime={test_regime!r}. "
            "Pass allow_regime_mismatch=True / --allow-regime-mismatch only for explicit transfer studies."
        )
    active_regime = test_regime or pol_regime

    pview_ev = get_policy_view(pol, regime=None if allow_regime_mismatch else active_regime)
    use_ora_ev = any(is_oracle_method(m) for m in pview_ev["thresholds"]) if include_oracles is None else bool(include_oracles)
    ev_methods = list(cfg["methods"]) + (list(ORACLES) if use_ora_ev else [])
    items, _ = _prepare_rollout_items(test_dir, truth=True, generate_on_the_fly=generate_on_the_fly)
    truth_dir = None if generate_on_the_fly else (test_dir.parent / (test_dir.name + "_truth"))

    w = parallel.resolve_workers(workers, len(items))
    chunk_sz = max(5, min(100, len(items) // max(1, w) or 1)) if w > 1 else len(items)
    chunks = _chunked(items, chunk_sz)
    tasks = [{
        "mode": "evaluate",
        "chunk_idx": ci,
        "items": ch,
        "model_dir": str(model_dir),
        "cache_dir": str(cache_dir) if cache_dir is not None else None,
        "methods": ev_methods,
        "pol": pol,
        "truth_dir": str(truth_dir) if truth_dir is not None else None,
        "regime": active_regime,
    } for ci, ch in enumerate(chunks)]
    chunk_outs = _run_chunked_with_resume(
        tasks, workers=w, resume_dir=out_dir if resume else None, journal_name="evaluate", desc="evaluate", log=log
    )

    rows, hostrows, flick, rt, calib, failures = [], [], [], [], [], []
    for co in chunk_outs:
        rows.extend(co["rows"]); hostrows.extend(co["hostrows"]); flick.extend(co["flick"])
        rt.extend(co["rt"]); calib.extend(co["calib"]); failures.extend(co["failures"])

    rows_df = pd.DataFrame(rows)
    if not rows_df.empty:
        rows_df = rows_df.sort_values(["rollout_id", "method"]).reset_index(drop=True)
    rows_df.to_csv(out_dir / "per_rollout_metrics.csv", index=False)

    host_df = pd.DataFrame(hostrows)
    if not host_df.empty:
        host_df = host_df.sort_values(["rollout_id", "method"]).reset_index(drop=True)
    host_df.to_csv(out_dir / "host_metrics.csv", index=False)

    flick_df = pd.DataFrame(flick)
    if not flick_df.empty:
        flick_df = flick_df.sort_values(["rollout_id", "method"]).reset_index(drop=True)
    flick_df.to_csv(out_dir / "flicker.csv", index=False)

    rt_df = pd.DataFrame(rt)
    if not rt_df.empty:
        rt_df = rt_df.sort_values(["rollout_id", "method"]).reset_index(drop=True)
    rt_df.to_csv(out_dir / "runtime.csv", index=False)

    calib_raw = pd.DataFrame(calib, columns=["rollout_id", "method", "bin", "n", "sum_p", "sum_j"])
    if not calib_raw.empty:
        calib_raw = calib_raw.sort_values(["method", "bin", "rollout_id"])
        agg = []
        for (m, b), grp in calib_raw.groupby(["method", "bin"], sort=True):
            agg.append({
                "method": m,
                "bin": int(b),
                "n": int(grp["n"].sum()),
                "sum_p": math.fsum(grp["sum_p"].tolist()),
                "sum_j": math.fsum(grp["sum_j"].tolist()),
            })
        calib_df = pd.DataFrame(agg).sort_values(["method", "bin"]).reset_index(drop=True)
    else:
        calib_df = pd.DataFrame(columns=["method", "bin", "n", "sum_p", "sum_j"])
    calib_df.to_csv(out_dir / "calibration_bins.csv", index=False)

    fail_df = pd.DataFrame(failures, columns=["rollout_id", "method", "params", "error"])
    if not fail_df.empty:
        fail_df = fail_df.sort_values(["rollout_id", "method"]).reset_index(drop=True)
    fail_df.to_csv(out_dir / "fit_failures.csv", index=False)

    wall_s = round(time.time() - t0_wall, 3)
    write_manifest(
        out_dir, model_dir, policy_dir, test_dir, cfg, pol, len(failures),
        wall_s=wall_s, allow_frozen=allow_frozen, allow_regime_mismatch=allow_regime_mismatch,
    )
    return out_dir


def write_manifest(
    out_dir,
    model_dir,
    policy_dir,
    test_dir,
    cfg,
    pol,
    n_fail,
    wall_s: float | None = None,
    allow_frozen: bool = False,
    allow_regime_mismatch: bool = False,
):
    test_man = json.loads((Path(test_dir) / "manifest.json").read_text(encoding="utf-8"))
    pview = get_policy_view(pol)
    wall_times = dict(cfg.get("wall_times", {}))
    if pview.get("wall_time_s") is not None:
        wall_times["calibrate_s"] = pview["wall_time_s"]
    if wall_s is not None:
        wall_times["evaluate_s"] = wall_s
    man = man_mod.build_manifest(
        out_dir=out_dir,
        config=test_man.get("config") or cfg.get("config"),
        config_hash=test_man.get("config_hash") or cfg.get("config_hash"),
        regime=test_man.get("regime") or pview.get("regime") or cfg.get("regime"),
        policy_regime=pview.get("regime"),
        beta_mode=cfg.get("beta_mode"),
        noise_mode=cfg.get("noise_mode", "ar_only"),
        factor_rank=cfg.get("factor_rank", 1),
        grid_file=cfg.get("grid_file"),
        grid_version=cfg.get("grid_version"),
        grid_hash=cfg.get("grid_hash"),
        candidate_table_hash=cfg.get("candidate_table_hash"),
        selected=cfg.get("selected"),
        edge_flags=cfg.get("edge_flags"),
        model_kind=cfg.get("kind", "frozen" if cfg.get("frozen") else "tuned"),
        model_frozen=bool(cfg.get("frozen", False)),
        allow_frozen=bool(allow_frozen),
        allow_regime_mismatch=bool(allow_regime_mismatch),
        seed_ranges={
            "dev": cfg.get("seed_ranges"),
            "calibration": pview.get("seed_ranges"),
            "test": test_man.get("seed_ranges"),
        },
        wall_times=wall_times,
        fit_failures=n_fail,
        fit_failures_test=n_fail,
        model_hash=pol["model_hash"],
        policy_hash=pview["calib_hash"],
        calib_hash=pview["calib_hash"],
        alpha=pview["alpha"],
        thresholds={m: c["threshold"] for m, c in pview["thresholds"].items()},
        test_manifest=test_man,
        model_dir=str(model_dir),
        policy_dir=str(policy_dir),
    )
    (Path(out_dir) / "experiment_manifest.json").write_text(json.dumps(man, indent=1, default=str), encoding="utf-8")


# ===================================================================== runtime benchmark
def benchmark(nuis_dir: Path | None, sizes=(10, 50, 100), reps: int = 3, out: Path = Path("results/runtime_scaling.csv")):
    rows = []
    for nc in sizes:
        cfg = SimConfig(n_canary=nc, n_hosts=nc + 90, n_affected=min(3, nc))
        healthy = [simulate(cfg, seeds.seed_for("study_X", s, 0), False)[0] for s in range(12)]
        nuis = fit_nuisance(healthy)
        for kind in ("hier", "indep"):
            ts = []
            for s in range(reps):
                roll, _ = simulate(cfg, seeds.seed_for("study_X", s, 1), True)
                a = adjust_roll(roll, nuis)
                ts.append(EffectDetector(nuis, EffectParams(kind=kind)).run(a).update_times_ms)
            ts = np.concatenate(ts)
            rows.append({
                "n_canaries": nc, "model": kind, "median_ms": np.median(ts), "p95_ms": np.quantile(ts, .95),
                "p99_ms": np.quantile(ts, .99), "machine": platform.processor() or platform.machine(),
            })
    df = pd.DataFrame(rows); Path(out).parent.mkdir(parents=True, exist_ok=True); df.to_csv(out, index=False)
    return df
