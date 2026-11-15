"""Linear-Gaussian Kalman filter (handbook Section 8).

  m- = F m ; P- = F P F' + Q
  v = r_obs - H_obs m- ; S = H_obs P- H_obs' + V_obs
  K = solve(S, H_obs P-)' ; m = m- + K v
  P = (I - K H) P- (I - K H)' + K V K'          (Joseph form)

Cholesky solves only; P is symmetrized each step; missing data => predict only.
Gaps of k grid intervals apply k transitions (never one).
"""
from __future__ import annotations

import numpy as np
from scipy.linalg import cho_factor, cho_solve


def symmetrize(P: np.ndarray) -> np.ndarray:
    return 0.5 * (P + P.T)


class KalmanFilter:
    def __init__(self, F: np.ndarray, Q: np.ndarray, m0: np.ndarray, P0: np.ndarray):
        self.F = np.asarray(F, float); self.Q = np.asarray(Q, float)
        self.m = np.asarray(m0, float).copy(); self.P = symmetrize(np.asarray(P0, float).copy())
        self.n = self.m.size
        self.min_eig_seen = np.inf
        self.floor_events = 0

    # ---- prediction ----
    def predict(self, k: int = 1) -> None:
        for _ in range(k):
            self.m = self.F @ self.m
            self.P = symmetrize(self.F @ self.P @ self.F.T + self.Q)

    # ---- update with a subset of observed coordinates ----
    def update(self, r_obs: np.ndarray, H_obs: np.ndarray, V_obs: np.ndarray) -> np.ndarray:
        """Returns the standardized innovation vector (for diagnostics)."""
        v = r_obs - H_obs @ self.m
        PHt = self.P @ H_obs.T
        S = symmetrize(H_obs @ PHt + V_obs)
        cf = cho_factor(S, lower=True, check_finite=False)
        K = cho_solve(cf, PHt.T, check_finite=False).T
        self.m = self.m + K @ v
        IKH = np.eye(self.n) - K @ H_obs
        self.P = symmetrize(IKH @ self.P @ IKH.T + K @ V_obs @ K.T)
        self._guard()
        L = np.linalg.cholesky(S)
        return np.linalg.solve(L, v)

    def step(self, r_obs=None, H_obs=None, V_obs=None, gap: int = 1):
        """Advance `gap` grid intervals; update only if an observation exists."""
        self.predict(gap)
        if r_obs is None or len(r_obs) == 0:
            return None
        return self.update(r_obs, H_obs, V_obs)

    def _guard(self, tol: float = 1e-12) -> None:
        w = np.linalg.eigvalsh(self.P)
        self.min_eig_seen = min(self.min_eig_seen, float(w[0]))
        if w[0] < -1e-8:
            raise FloatingPointError(f"covariance materially non-PSD (min eig {w[0]:.3e})")
        if w[0] < tol:                                   # tiny negative: floor and LOG
            self.floor_events += 1
            ev, U = np.linalg.eigh(self.P)
            self.P = symmetrize((U * np.maximum(ev, tol)) @ U.T)

    def copy(self) -> "KalmanFilter":
        k = KalmanFilter(self.F, self.Q, self.m, self.P)
        k.min_eig_seen, k.floor_events = self.min_eig_seen, self.floor_events
        return k
