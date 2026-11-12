"""Data contracts (handbook Section 4).

INFERENCE MODULES MAY ONLY IMPORT FROM THIS FILE, NEVER FROM simulate.py's Truth.
`Rollout` is everything a detector is allowed to see. Truth lives in simulate.py
and is read only by metrics.py / experiments.py (evaluator side).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

KAPPA = float(np.log(1.02))          # harmful-effect boundary, ~0.0198 (handbook Sec 3)
D_MIN = 15                           # qualifying event duration, minutes
TELEMETRY_COLUMNS = ["rollout_id", "host_id", "class_id", "event_time", "arrival_time",
                     "exposed", "latency_ms", "workload", "request_count", "observed"]
ROLES = ("smoke", "dev", "calibration", "null_validation", "test")


@dataclass
class Rollout:
    """Detector-visible rollout. Hosts 0..n_canary-1 are canaries, the rest controls.

    y             (T, N) log latency, NaN where not observed at all
    x             (T,)   measured log workload
    observed      (T, N) record exists (event-time view)
    decision_obs  (T, N) record had ARRIVED by its decision timestamp (what a streaming detector may use)
    class_id      (N,)   fixed metadata host class
    exposed       (N,)   canary flag (fixed rollout membership)
    t0            first post-rollout index; pre-period is [0, t0)
    """
    rollout_id: str
    y: np.ndarray
    x: np.ndarray
    observed: np.ndarray
    decision_obs: np.ndarray
    class_id: np.ndarray
    exposed: np.ndarray
    t0: int
    request_count: np.ndarray
    meta: dict = field(default_factory=dict)

    @property
    def T(self) -> int:
        return self.y.shape[0]

    @property
    def N(self) -> int:
        return self.y.shape[1]

    @property
    def canary_idx(self) -> np.ndarray:
        return np.flatnonzero(self.exposed)

    @property
    def control_idx(self) -> np.ndarray:
        return np.flatnonzero(~self.exposed)

    # ---------------- persistence (npz is the bulk format, CSV is the contract format)
    def save_npz(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, rollout_id=self.rollout_id, y=self.y, x=self.x,
                            observed=self.observed, decision_obs=self.decision_obs,
                            class_id=self.class_id, exposed=self.exposed, t0=self.t0,
                            request_count=self.request_count, meta=json.dumps(self.meta))

    @staticmethod
    def load_npz(path: Path) -> "Rollout":
        z = np.load(path, allow_pickle=False)
        return Rollout(str(z["rollout_id"]), z["y"], z["x"], z["observed"], z["decision_obs"],
                       z["class_id"], z["exposed"], int(z["t0"]), z["request_count"],
                       json.loads(str(z["meta"])))

    def to_telemetry(self, arrival_delay: np.ndarray | None = None) -> pd.DataFrame:
        T, N = self.y.shape
        tt, hh = np.meshgrid(np.arange(T), np.arange(N), indexing="ij")
        if arrival_delay is None:   # late records are those observed but not usable at decision time
            arrival_delay = np.where(self.observed & ~self.decision_obs, self.meta.get("late_delay", 3), 0)
        delay = arrival_delay
        df = pd.DataFrame({
            "rollout_id": self.rollout_id, "host_id": hh.ravel(),
            "class_id": self.class_id[hh.ravel()], "event_time": tt.ravel(),
            "arrival_time": (tt + delay).ravel(), "exposed": self.exposed[hh.ravel()],
            "latency_ms": np.exp(self.y).ravel(), "workload": self.x[tt.ravel()],
            "request_count": self.request_count.ravel(), "observed": self.observed.ravel()})
        return df[TELEMETRY_COLUMNS]

    def metadata(self) -> dict:
        return {"rollout_id": self.rollout_id, "t0": self.t0, "T": self.T, "n_hosts": self.N,
                "canary_hosts": self.canary_idx.tolist(), "class_id": self.class_id.tolist(),
                "units": "latency_ms is exp(log-latency); one-minute windows", **self.meta}


def telemetry_to_rollout(df: pd.DataFrame, meta: dict) -> Rollout:
    """Rebuild a Rollout from contract-format CSV + metadata (round-trip test)."""
    T, N = meta["T"], meta["n_hosts"]
    df = df.sort_values(["event_time", "host_id"])
    assert not df.duplicated(["event_time", "host_id"]).any(), "duplicate host-window keys"
    y = np.log(df["latency_ms"].to_numpy()).reshape(T, N)
    observed = df["observed"].to_numpy().reshape(T, N).astype(bool)
    arrival = df["arrival_time"].to_numpy().reshape(T, N)
    event = df["event_time"].to_numpy().reshape(T, N)
    decision_obs = observed & (arrival <= event)       # late records unusable at decision time
    cls = np.array(meta["class_id"]); exposed = np.zeros(N, bool); exposed[meta["canary_hosts"]] = True
    skip = ("rollout_id", "t0", "T", "n_hosts", "canary_hosts", "class_id", "units")
    return Rollout(meta["rollout_id"], y, df["workload"].to_numpy().reshape(T, N)[:, 0], observed,
                   decision_obs, cls, exposed, meta["t0"],
                   df["request_count"].to_numpy().reshape(T, N),
                   {k: v for k, v in meta.items() if k not in skip})


def file_hash(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dict_hash(d: dict) -> str:
    return hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()[:16]


def dir_hash(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(Path(p).name.encode()); h.update(Path(p).read_bytes())
    return h.hexdigest()[:16]
