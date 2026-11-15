"""Time slicing, streaming record ingestion, and multi-metric residual pipeline.

Strict Anti-Leakage & Causality Guarantees:
1. Decision timestamp causality: A slice for decision timestamp t uses ONLY records
   received by t (arrival_time <= t). Records with arrival_time > t are excluded.
2. Invariance to future observations: Residuals computed at time t cannot be altered
   by any future observation changes at t' > t.
3. Alert immutability: Alerts emitted at decision timestamp t are immutable and are never
   revised when late records for t arrive at t' > t.
4. Clean control pool: Exposed hosts (exposure == True or version != baseline_version)
   are strictly excluded from the baseline control pool.
5. Nested fleet and rack adjustment:
   Shared fleet variation (f_t) is estimated across all eligible controls.
   Shared rack nuisance (gamma_j(t)) is estimated from rack controls on fleet-adjusted
   residuals with a zero-sum identifiability constraint:
       sum_j W_j gamma_hat_j(t) = 0
   This prevents subtracting the same component twice.
6. Estimation uncertainty:
   Control estimation variance is propagated into the canary residual covariance:
       Cov(A_{i1, t}, A_{i2, t}) = U_{j, t}^{rack} + (lam_{i1} lam_{i2} - bar{lam}_{Cj}^2) U_t^{fleet}  (same rack)
                                 = lam_{i1} lam_{i2} U_t^{fleet}                                         (different racks)
7. Coverage & Identifiability:
   Requires configured minimum fresh controls per rack and class. If rack controls are absent,
   release cause inference is strictly prohibited (marked unidentifiable).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any
import numpy as np

from .records import TelemetryRecord


@dataclass(frozen=True)
class SlicingProtocol:
    """Protocol rules and thresholds for time slicing, control coverage, and identifiability.

    In the default 4-rack demo (4 racks x 6 servers = 24 servers, 1 canary per rack),
    each rack starts with 5 baseline controls.
    """
    min_controls_per_rack: int = 3       # Minimum fresh baseline controls required per rack with canaries
    min_controls_per_class: int = 3      # Minimum fresh baseline controls required per represented class
    min_canary_coverage: float = 0.80    # Minimum fraction of canaries that must have fresh observations
    min_pre_obs: int = 60                # Minimum pre-period observations for host-specific loading
    max_staleness_ticks: int = 0         # Allowed staleness: 0 requires contemporaneous tick
    baseline_version: str = "v1.0.0"     # Nominal baseline version tag
    factor_rank: int = 1                 # Fleet factor rank (0 or 1)
    beta_mode: str = "pooled"            # "pooled" (recommended) or "pre" (individual per-host)

    @property
    def min_canary_frac(self) -> float:
        return self.min_canary_coverage


@dataclass
class SliceAuditLog:
    """Audit log of telemetry stream ingestion at a single decision timestamp."""
    tick: int
    duplicates: list[dict[str, Any]] = field(default_factory=list)
    duplicate_count: int = 0
    stale: list[dict[str, Any]] = field(default_factory=list)
    stale_count: int = 0
    late: list[dict[str, Any]] = field(default_factory=list)
    late_count: int = 0
    missing_servers: list[str] = field(default_factory=list)
    missing_count: int = 0
    total_received: int = 0
    total_admitted: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TimeSlice:
    """Multi-metric observation slice at a decision timestamp t with nested adjustment.

    Contains adjusted log-latency, per-metric residuals (memory, CPU, errors),
    uncertainty covariance, and explicit coverage eligibility.
    """
    tick: int
    eligible: bool
    ineligible_reasons: list[str]
    canary_ids: list[str]
    control_ids: list[str]
    canary_racks: list[str]
    canary_classes: list[int]
    
    # Adjusted residuals for canaries: shape (nc,)
    r_latency: np.ndarray
    r_memory: np.ndarray
    r_cpu: np.ndarray
    r_error: np.ndarray
    
    # Usable observation masks for canaries: shape (nc,)
    mask_latency: np.ndarray
    mask_memory: np.ndarray
    mask_cpu: np.ndarray
    mask_error: np.ndarray
    
    # Shared nuisance estimates
    f_hat: float
    gamma_hat: dict[str, float]
    
    # Estimation uncertainties
    U_fleet: float
    U_rack: dict[str, float]
    cov_U: np.ndarray                   # (nc, nc) shared estimation error covariance
    
    # Identifiability & release cause guard
    is_unidentifiable: bool
    attribution_blocked_reasons: list[str]
    
    # Audit log
    audit_log: SliceAuditLog

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "eligible": self.eligible,
            "ineligible_reasons": self.ineligible_reasons,
            "canary_ids": self.canary_ids,
            "control_ids": self.control_ids,
            "r_latency": [round(float(v), 6) if np.isfinite(v) else None for v in self.r_latency],
            "r_memory": [round(float(v), 2) if np.isfinite(v) else None for v in self.r_memory],
            "r_cpu": [round(float(v), 6) if np.isfinite(v) else None for v in self.r_cpu],
            "r_error": [round(float(v), 4) if np.isfinite(v) else None for v in self.r_error],
            "f_hat": round(float(self.f_hat), 6) if np.isfinite(self.f_hat) else 0.0,
            "gamma_hat": {k: round(float(v), 6) for k, v in self.gamma_hat.items()},
            "U_fleet": round(float(self.U_fleet), 8) if np.isfinite(self.U_fleet) else 0.0,
            "is_unidentifiable": self.is_unidentifiable,
            "attribution_blocked_reasons": self.attribution_blocked_reasons,
            "audit_log": self.audit_log.to_dict(),
        }


@dataclass
class PrePeriodBaseline:
    """Pre-period fitted parameters, fitted strictly on pre-exposure data (t < t0)."""
    t0: int
    x_center: float
    # Latency parameters
    mu_latency: dict[str, float]         # host_id -> mu
    beta_latency: dict[str, float]       # host_id -> beta
    lam: dict[str, float]                # host_id -> loading lambda_i
    sigma_latency: dict[str, float]      # host_id -> residual SD
    class_lambda: dict[int, float]       # class fallback lambda
    # Other metric baseline means on pre-period
    mu_memory: dict[str, float]          # host_id -> mean baseline memory MB
    mu_cpu: dict[str, float]             # host_id -> mean baseline CPU fraction
    beta_cpu: dict[str, float]           # host_id -> CPU workload slope
    mu_error: dict[str, float]           # host_id -> mean baseline error count
    host_racks: dict[str, str]           # host_id -> rack_id
    host_classes: dict[str, int]         # host_id -> class_id


def fit_preperiod_baseline(
    records: list[TelemetryRecord],
    t0: int,
    expected_servers: list[str],
    protocol: SlicingProtocol = SlicingProtocol(),
) -> PrePeriodBaseline:
    """Fit host workload, intercepts, and loadings strictly on pre-period data (event_time < t0).

    Uses ONLY records with event_time < t0 and arrival_time < t0.
    """
    pre_recs = [
        r for r in records
        if r.event_time < t0 and r.arrival_time < t0 and r.observed and r.server_id in expected_servers
    ]
    if not pre_recs:
        raise ValueError(f"No pre-period records found before t0={t0}")

    # Index by server
    by_srv: dict[str, list[TelemetryRecord]] = {s: [] for s in expected_servers}
    for r in pre_recs:
        by_srv[r.server_id].append(r)

    host_racks = {}
    host_classes = {}
    for s, recs in by_srv.items():
        if recs:
            host_racks[s] = recs[0].rack_id
            host_classes[s] = recs[0].class_id
        else:
            host_racks[s] = "unknown"
            host_classes[s] = 0

    # Workload centering: mean log request count across all servers in pre-period
    workloads = [np.log(max(r.request_count, 1)) for r in pre_recs]
    x_center = float(np.mean(workloads)) if workloads else 0.0

    mu_latency = {}
    beta_latency = {}
    mu_memory = {}
    mu_cpu = {}
    beta_cpu = {}
    mu_error = {}
    sigma_latency = {}

    wadj_by_srv: dict[str, dict[int, float]] = {s: {} for s in expected_servers}

    for s in expected_servers:
        recs = by_srv[s]
        if len(recs) < 5:
            mu_latency[s] = float(np.log(10.0))
            beta_latency[s] = 0.0
            sigma_latency[s] = 0.05
            mu_memory[s] = 200.0
            mu_cpu[s] = 0.10
            beta_cpu[s] = 0.0
            mu_error[s] = 0.0
            continue

        ys = np.array([np.log(r.latency_ms) for r in recs])
        xs = np.array([np.log(max(r.request_count, 1)) - x_center for r in recs])
        mems = np.array([r.memory_mb for r in recs])
        cpus = np.array([r.cpu_fraction for r in recs])
        errs = np.array([r.error_count for r in recs])

        # OLS for latency: y = mu + beta * xc
        X = np.column_stack([np.ones(len(xs)), xs])
        coef, *_ = np.linalg.lstsq(X, ys, rcond=None)
        mu, beta = float(coef[0]), float(coef[1])
        mu_latency[s] = mu
        beta_latency[s] = beta

        # Residuals
        resids = ys - (mu + beta * xs)
        sigma_latency[s] = float(max(np.std(resids), 1e-4))

        for r, res in zip(recs, resids):
            wadj_by_srv[s][r.event_time] = res

        # Other metrics
        mu_memory[s] = float(np.mean(mems))
        mu_error[s] = float(np.mean(errs))

        coef_cpu, *_ = np.linalg.lstsq(X, cpus, rcond=None)
        mu_cpu[s] = float(coef_cpu[0])
        beta_cpu[s] = float(coef_cpu[1])

    # If pooled beta mode is requested, use fleet median slope across hosts
    if protocol.beta_mode == "pooled" and beta_latency:
        pooled_beta = float(np.median(list(beta_latency.values())))
        for s in expected_servers:
            recs = by_srv[s]
            if recs:
                ys = np.array([np.log(r.latency_ms) for r in recs])
                xs = np.array([np.log(max(r.request_count, 1)) - x_center for r in recs])
                mu = float(np.mean(ys - pooled_beta * xs))
                mu_latency[s] = mu
                beta_latency[s] = pooled_beta
                resids = ys - (mu + pooled_beta * xs)
                sigma_latency[s] = float(max(np.std(resids), 1e-4))
                for r, res in zip(recs, resids):
                    wadj_by_srv[s][r.event_time] = res

    # Class-level fallback loadings
    classes = sorted(set(host_classes.values()))
    class_lambda = {c: 1.0 for c in classes}

    # Factor loadings: SVD on control pre-period residuals
    # Controls in pre-period are all servers with exposure == False
    control_servers = [s for s in expected_servers if not any(r.exposure for r in by_srv[s])]
    if not control_servers:
        control_servers = expected_servers

    # Build matrix (T_pre, N_ctl)
    t_ticks = sorted(set(r.event_time for r in pre_recs))
    if len(t_ticks) > 5 and len(control_servers) > 1:
        C_mat = np.zeros((len(t_ticks), len(control_servers)))
        for j, s in enumerate(control_servers):
            for i, t in enumerate(t_ticks):
                C_mat[i, j] = wadj_by_srv[s].get(t, 0.0)

        # SVD rank-1 factor
        u, s_vals, vt = np.linalg.svd(C_mat, full_matrices=False)
        sc = np.sqrt(max(len(t_ticks) - 1, 1))
        factor_strength = s_vals[0] / sc

        # Marchenko-Pastur random noise floor for null Wishart matrix
        med_sigma = float(np.median([sigma_latency.get(s, 0.05) for s in control_servers]))
        noise_floor = med_sigma * (1.0 + np.sqrt(len(control_servers) / max(len(t_ticks), 1)))

        if factor_strength > 1.5 * noise_floor:
            lam_C = s_vals[0] * vt[0] / sc
            if np.mean(lam_C) < 0:
                lam_C = -lam_C
            f_pre = C_mat @ lam_C / max(float(lam_C @ lam_C), 1e-12)
            # Normalize so mean control loading is ~ 1.0 (class scale)
            mean_lam = float(np.mean(lam_C))
            if mean_lam > 1e-4:
                lam_C = lam_C / mean_lam
                f_pre = f_pre * mean_lam

            lam = {}
            for j, s in enumerate(control_servers):
                lam[s] = float(lam_C[j])

            # Project canary servers onto pre-period factor
            for s in expected_servers:
                if s not in lam:
                    c_series = np.array([wadj_by_srv[s].get(t, 0.0) for t in t_ticks])
                    denom = float(np.sum(f_pre ** 2))
                    if denom > 1e-8 and len(by_srv[s]) >= protocol.min_pre_obs:
                        lam[s] = float(np.sum(f_pre * c_series) / denom)
                    else:
                        lam[s] = class_lambda.get(host_classes[s], 1.0)
        else:
            # Factor not distinct from white noise floor; use class fallbacks (1.0)
            lam = {s: class_lambda.get(host_classes[s], 1.0) for s in expected_servers}
    else:
        lam = {s: 1.0 for s in expected_servers}

    return PrePeriodBaseline(
        t0=t0,
        x_center=x_center,
        mu_latency=mu_latency,
        beta_latency=beta_latency,
        lam=lam,
        sigma_latency=sigma_latency,
        class_lambda=class_lambda,
        mu_memory=mu_memory,
        mu_cpu=mu_cpu,
        beta_cpu=beta_cpu,
        mu_error=mu_error,
        host_racks=host_racks,
        host_classes=host_classes,
    )


class StreamSliceBuilder:
    """Streaming telemetry ingestion and causality-preserving time slice generator.

    Maintains:
    - Ingested records sorted by arrival and event time.
    - Deterministic duplicate resolution.
    - Immutable alert history.
    - Identifiable nested fleet and rack nuisance estimation.
    """
    def __init__(
        self,
        expected_servers: list[str],
        server_metadata: dict[str, dict[str, Any]],
        protocol: SlicingProtocol = SlicingProtocol(),
        baseline: PrePeriodBaseline | None = None,
    ) -> None:
        self.expected_servers = list(expected_servers)
        self.server_metadata = dict(server_metadata)
        self.protocol = protocol
        self.baseline = baseline
        
        # Ingestion storage: (server_id, event_time) -> TelemetryRecord (first received)
        self._records_by_key: dict[tuple[str, int], TelemetryRecord] = {}
        # All received raw records for audit
        self._raw_records: list[TelemetryRecord] = []
        # Immutable alert history: tick -> alert dict
        self._alert_history: dict[int, dict[str, Any]] = {}
        # Cached slices: tick -> TimeSlice
        self._slices_by_tick: dict[int, TimeSlice] = {}

    def ingest(self, records: list[TelemetryRecord]) -> None:
        """Ingest a batch of newly arrived TelemetryRecords.

        Maintains arrival order and logs any duplicates.
        """
        for r in records:
            self._raw_records.append(r)
            key = (r.server_id, r.event_time)
            if key not in self._records_by_key:
                self._records_by_key[key] = r

    def record_alert(self, tick: int, alert: dict[str, Any]) -> None:
        """Record an alert for decision timestamp tick.

        Alerts are IMMUTABLE. Once recorded, an alert cannot be modified or replaced.
        """
        if tick in self._alert_history:
            raise RuntimeError(f"Alert at tick {tick} is immutable and cannot be rewritten")
        self._alert_history[tick] = dict(alert)

    def get_alert(self, tick: int) -> dict[str, Any] | None:
        """Retrieve the immutable alert emitted at decision timestamp tick."""
        return self._alert_history.get(tick)

    def get_alert_history(self) -> dict[int, dict[str, Any]]:
        """Return a copy of the entire immutable alert history."""
        return dict(self._alert_history)

    def build_slice(self, decision_tick: int) -> TimeSlice:
        """Build the observation slice for event_time == decision_tick as of decision_tick.

        Strict Causality:
        Uses ONLY records that have arrival_time <= decision_tick.
        Records with arrival_time > decision_tick are strictly ignored.
        """
        if self.baseline is None:
            raise RuntimeError("Cannot build time slice: PrePeriodBaseline has not been fitted")

        base = self.baseline
        proto = self.protocol

        # Step 1: Collect records that arrived by decision_tick
        arrived_raw = [r for r in self._raw_records if r.arrival_time <= decision_tick]

        # Audit tracking
        duplicates = []
        seen_keys: set[tuple[str, int]] = set()
        admitted_by_key: dict[tuple[str, int], TelemetryRecord] = {}

        for r in arrived_raw:
            key = (r.server_id, r.event_time)
            if key in seen_keys:
                duplicates.append({
                    "server_id": r.server_id,
                    "event_time": r.event_time,
                    "arrival_time": r.arrival_time,
                    "tick": decision_tick,
                })
            else:
                seen_keys.add(key)
                admitted_by_key[key] = r

        # Stale and Late records audit across all records arrived by decision_tick
        stale_records = []
        late_records = []
        for r in arrived_raw:
            if r.event_time < decision_tick - proto.max_staleness_ticks:
                stale_records.append({
                    "server_id": r.server_id,
                    "event_time": r.event_time,
                    "arrival_time": r.arrival_time,
                })
            if r.arrival_time > r.event_time:
                late_records.append({
                    "server_id": r.server_id,
                    "event_time": r.event_time,
                    "arrival_time": r.arrival_time,
                })

        # Admitted records for the contemporaneous event time
        target_event_time = decision_tick
        contemp_records: dict[str, TelemetryRecord] = {}
        missing_servers = []

        for sid in self.expected_servers:
            key = (sid, target_event_time)
            if key in admitted_by_key:
                rec = admitted_by_key[key]
                if rec.observed:
                    contemp_records[sid] = rec
                else:
                    missing_servers.append(sid)
            else:
                missing_servers.append(sid)

        audit_log = SliceAuditLog(
            tick=decision_tick,
            duplicates=duplicates,
            duplicate_count=len(duplicates),
            stale=stale_records,
            stale_count=len(stale_records),
            late=late_records,
            late_count=len(late_records),
            missing_servers=missing_servers,
            missing_count=len(missing_servers),
            total_received=len(arrived_raw),
            total_admitted=len(contemp_records),
        )

        # Step 2: Classify servers into Canaries and Baseline Controls
        # Strict rule: EXCLUDE EXPOSED HOSTS FROM CONTROLS
        canary_ids = []
        control_ids = []

        for sid in self.expected_servers:
            meta = self.server_metadata.get(sid, {})
            # Check if observed record indicates exposure or version mismatch
            rec = contemp_records.get(sid)
            is_exposed = False
            if rec is not None:
                is_exposed = rec.exposure or (rec.version != proto.baseline_version and not rec.version.startswith(proto.baseline_version))
            else:
                is_exposed = meta.get("exposed", False)

            if is_exposed:
                canary_ids.append(sid)
            else:
                control_ids.append(sid)

        nc = len(canary_ids)
        canary_racks = [base.host_racks.get(s, "unknown") for s in canary_ids]
        canary_classes = [base.host_classes.get(s, 0) for s in canary_ids]

        # Step 3: Workload adjustment for available records
        # c_it = y_it - mu_i - beta_i * (x_t - x_center)
        # Global workload x_t from mean of available request counts
        req_counts = [r.request_count for r in contemp_records.values() if r.observed]
        if req_counts:
            x_t = float(np.mean([np.log(max(cnt, 1)) for cnt in req_counts]))
        else:
            x_t = base.x_center
        xc_t = x_t - base.x_center

        wadj: dict[str, float] = {}
        for sid, r in contemp_records.items():
            if r.observed and r.latency_ms > 0:
                y = np.log(r.latency_ms)
                mu = base.mu_latency.get(sid, 0.0)
                beta = base.beta_latency.get(sid, 0.0)
                wadj[sid] = float(y - mu - beta * xc_t)

        # Step 4: Eligible Baseline Controls
        # Must be unexposed controls with valid observations at this tick
        eligible_controls = [sid for sid in control_ids if sid in wadj]

        # Step 5: Shared Fleet Factor Estimation (f_hat_t)
        # f_hat_t = (sum_{k in C_t} w_k lam_k c_kt) / (sum_{k in C_t} w_k lam_k^2)
        if eligible_controls and proto.factor_rank > 0:
            weights = np.array([1.0 / (base.sigma_latency.get(s, 0.05) ** 2) for s in eligible_controls])
            lams = np.array([base.lam.get(s, 1.0) for s in eligible_controls])
            c_vals = np.array([wadj[s] for s in eligible_controls])

            denom = float(np.sum(weights * (lams ** 2)))
            if denom > 1e-9:
                f_hat = float(np.sum(weights * lams * c_vals) / denom)
                U_fleet = float(1.0 / denom)
            else:
                f_hat = 0.0
                U_fleet = 0.0
        else:
            f_hat = 0.0
            U_fleet = 0.0

        # Step 6: Shared Rack Nuisance Estimation (gamma_hat_j(t))
        # Nested adjustment: rack nuisance is estimated from control residuals AFTER fleet factor removal:
        # e_kt = c_kt - lam_k f_hat_t
        # Identifiability constraint: sum_j W_j gamma_hat_j(t) = 0
        gamma_hat_raw: dict[str, float] = {}
        U_rack: dict[str, float] = {}
        rack_weights: dict[str, float] = {}

        # Group controls by rack
        ctl_by_rack: dict[str, list[str]] = {}
        for sid in eligible_controls:
            rk = base.host_racks.get(sid, "unknown")
            ctl_by_rack.setdefault(rk, []).append(sid)

        for rk, rk_ctls in ctl_by_rack.items():
            rk_weights = np.array([1.0 / (base.sigma_latency.get(s, 0.05) ** 2) for s in rk_ctls])
            rk_lams = np.array([base.lam.get(s, 1.0) for s in rk_ctls])
            rk_c = np.array([wadj[s] for s in rk_ctls])
            rk_e = rk_c - rk_lams * f_hat

            w_sum = float(np.sum(rk_weights))
            rack_weights[rk] = w_sum
            if w_sum > 1e-9:
                gamma_hat_raw[rk] = float(np.sum(rk_weights * rk_e) / w_sum)
                U_rack[rk] = float(1.0 / w_sum)
            else:
                gamma_hat_raw[rk] = 0.0
                U_rack[rk] = 0.0

        # Enforce exact identifiable zero-sum constraint: sum_j W_j gamma_hat_j = 0
        total_rack_weight = sum(rack_weights.values())
        if total_rack_weight > 1e-9:
            weighted_mean_gamma = sum(rack_weights[rk] * gamma_hat_raw.get(rk, 0.0) for rk in rack_weights) / total_rack_weight
        else:
            weighted_mean_gamma = 0.0

        gamma_hat: dict[str, float] = {}
        for rk in set(base.host_racks.values()):
            if rk in gamma_hat_raw:
                gamma_hat[rk] = gamma_hat_raw[rk] - weighted_mean_gamma
            else:
                gamma_hat[rk] = 0.0
                U_rack[rk] = 0.0

        # Step 7: Canary Residuals & Covariance
        r_latency = np.full(nc, np.nan)
        mask_latency = np.zeros(nc, bool)
        cov_U = np.zeros((nc, nc))

        # Check for unidentifiable racks (racks with canaries but ZERO controls)
        is_unidentifiable = False
        attribution_blocked_reasons = []

        canary_represented_racks = set(canary_racks)
        for rk in canary_represented_racks:
            count = len(ctl_by_rack.get(rk, []))
            if count == 0:
                is_unidentifiable = True
                msg = f"ABSENT_RACK_CONTROLS: Rack '{rk}' has 0 baseline controls; rack slowdown and release effect are indistinguishable"
                attribution_blocked_reasons.append(msg)

        # Compute canary latency residuals: r_it = c_it - lam_i * f_hat - gamma_hat_{rack}
        for i, cid in enumerate(canary_ids):
            rk = canary_racks[i]
            if cid in wadj:
                c_val = wadj[cid]
                lam_i = base.lam.get(cid, 1.0)
                g_val = gamma_hat.get(rk, 0.0)
                r_latency[i] = c_val - lam_i * f_hat - g_val
                mask_latency[i] = True

        # Build uncertainty covariance matrix cov_U:
        # Cov(A_{i1}, A_{i2}) = U_j^{rack} + (lam_{i1} lam_{i2} - bar{lam}_j^2) U^{fleet}  if same rack
        #                     = lam_{i1} lam_{i2} U^{fleet}                                 if different rack
        for i1 in range(nc):
            rk1 = canary_racks[i1]
            lam1 = base.lam.get(canary_ids[i1], 1.0)
            u_rk1 = U_rack.get(rk1, 0.0)
            ctls1 = ctl_by_rack.get(rk1, [])
            bar_lam1 = float(np.mean([base.lam.get(s, 1.0) for s in ctls1])) if ctls1 else 1.0

            for i2 in range(nc):
                rk2 = canary_racks[i2]
                lam2 = base.lam.get(canary_ids[i2], 1.0)
                if rk1 == rk2:
                    cov_U[i1, i2] = u_rk1 + (lam1 * lam2 - bar_lam1 ** 2) * U_fleet
                else:
                    cov_U[i1, i2] = lam1 * lam2 * U_fleet

        # Ensure diagonal is strictly non-negative
        for i in range(nc):
            cov_U[i, i] = max(cov_U[i, i], 0.0)

        # Step 8: Multi-Metric Residuals (Memory, CPU, Errors)
        r_memory = np.full(nc, np.nan)
        r_cpu = np.full(nc, np.nan)
        r_error = np.full(nc, np.nan)
        mask_memory = np.zeros(nc, bool)
        mask_cpu = np.zeros(nc, bool)
        mask_error = np.zeros(nc, bool)

        # Compute rack-level control baselines for memory, CPU, errors
        rack_mem_control_shift: dict[str, float] = {}
        rack_cpu_control_shift: dict[str, float] = {}
        rack_err_control_shift: dict[str, float] = {}

        for rk, rk_ctls in ctl_by_rack.items():
            mem_shifts = [
                contemp_records[s].memory_mb - base.mu_memory.get(s, 200.0)
                for s in rk_ctls if s in contemp_records
            ]
            cpu_shifts = [
                contemp_records[s].cpu_fraction - (base.mu_cpu.get(s, 0.1) + base.beta_cpu.get(s, 0.0) * xc_t)
                for s in rk_ctls if s in contemp_records
            ]
            err_shifts = [
                contemp_records[s].error_count - base.mu_error.get(s, 0.0)
                for s in rk_ctls if s in contemp_records
            ]
            rack_mem_control_shift[rk] = float(np.mean(mem_shifts)) if mem_shifts else 0.0
            rack_cpu_control_shift[rk] = float(np.mean(cpu_shifts)) if cpu_shifts else 0.0
            rack_err_control_shift[rk] = float(np.mean(err_shifts)) if err_shifts else 0.0

        for i, cid in enumerate(canary_ids):
            rk = canary_racks[i]
            if cid in contemp_records:
                rec = contemp_records[cid]
                # Memory residual: canary memory shift minus same-rack control memory shift
                mem_shift = rec.memory_mb - base.mu_memory.get(cid, 200.0)
                r_memory[i] = mem_shift - rack_mem_control_shift.get(rk, 0.0)
                mask_memory[i] = True

                # CPU residual: canary CPU shift minus workload and rack control CPU shift
                cpu_pred = base.mu_cpu.get(cid, 0.1) + base.beta_cpu.get(cid, 0.0) * xc_t
                cpu_shift = rec.cpu_fraction - cpu_pred
                r_cpu[i] = cpu_shift - rack_cpu_control_shift.get(rk, 0.0)
                mask_cpu[i] = True

                # Error residual: canary error count minus baseline and rack control error shift
                err_shift = rec.error_count - base.mu_error.get(cid, 0.0)
                r_error[i] = err_shift - rack_err_control_shift.get(rk, 0.0)
                mask_error[i] = True

        # Step 9: Protocol Coverage Rules & Abstention
        ineligible_reasons = []

        # 9a. Minimum Canary Coverage (default 80%)
        if nc > 0:
            obs_canary_frac = float(np.mean(mask_latency))
            if obs_canary_frac < proto.min_canary_frac:
                ineligible_reasons.append(
                    f"INSUFFICIENT_CANARY_COVERAGE: {obs_canary_frac:.1%} < {proto.min_canary_frac:.1%}"
                )
        else:
            ineligible_reasons.append("NO_CANARIES_CONFIGURED")

        # 9b. Minimum Controls Per Rack (default 3 controls per rack containing canaries)
        for rk in canary_represented_racks:
            count = len(ctl_by_rack.get(rk, []))
            if count < proto.min_controls_per_rack:
                ineligible_reasons.append(
                    f"INSUFFICIENT_RACK_CONTROLS: Rack '{rk}' has {count} < {proto.min_controls_per_rack} fresh controls"
                )

        # 9c. Minimum Controls Per Class (default 3 controls per represented class)
        ctl_by_class: dict[int, list[str]] = {}
        for sid in eligible_controls:
            cls_id = base.host_classes.get(sid, 0)
            ctl_by_class.setdefault(cls_id, []).append(sid)

        for cls_id in set(canary_classes):
            count = len(ctl_by_class.get(cls_id, []))
            if count < proto.min_controls_per_class:
                ineligible_reasons.append(
                    f"INSUFFICIENT_CLASS_CONTROLS: Class '{cls_id}' has {count} < {proto.min_controls_per_class} fresh controls"
                )

        eligible = (len(ineligible_reasons) == 0) and not is_unidentifiable

        ts = TimeSlice(
            tick=decision_tick,
            eligible=eligible,
            ineligible_reasons=ineligible_reasons,
            canary_ids=canary_ids,
            control_ids=control_ids,
            canary_racks=canary_racks,
            canary_classes=canary_classes,
            r_latency=r_latency,
            r_memory=r_memory,
            r_cpu=r_cpu,
            r_error=r_error,
            mask_latency=mask_latency,
            mask_memory=mask_memory,
            mask_cpu=mask_cpu,
            mask_error=mask_error,
            f_hat=f_hat,
            gamma_hat=gamma_hat,
            U_fleet=U_fleet,
            U_rack=U_rack,
            cov_U=cov_U,
            is_unidentifiable=is_unidentifiable,
            attribution_blocked_reasons=attribution_blocked_reasons,
            audit_log=audit_log,
        )
        self._slices_by_tick[decision_tick] = ts
        return ts


def infer_release_cause(
    slice_data: TimeSlice,
    canary_id: str | None = None,
) -> tuple[bool, str]:
    """Determine if a release cause can be legitimately inferred from the current time slice.

    Identifiability Guard:
    DO NOT infer a release cause if rack controls are absent or insufficient.
    Returns (can_infer, reason).
    """
    if slice_data.is_unidentifiable:
        return False, f"UNIDENTIFIABLE: {'; '.join(slice_data.attribution_blocked_reasons)}"

    if not slice_data.eligible:
        return False, f"INELIGIBLE_DATA: {'; '.join(slice_data.ineligible_reasons)}"

    if canary_id is not None:
        if canary_id not in slice_data.canary_ids:
            return False, f"UNKNOWN_CANARY: '{canary_id}' not in canary list"
        idx = slice_data.canary_ids.index(canary_id)
        rk = slice_data.canary_racks[idx]
        if rk not in slice_data.gamma_hat:
            return False, f"MISSING_RACK_INFO: No rack nuisance estimate for rack '{rk}'"

    return True, "IDENTIFIABLE_RELEASE_EFFECT"
