"""Telemetry package: typed observable multi-metric records and streaming utilities."""
from __future__ import annotations

from .records import TelemetryRecord
from .slicing import (
    SlicingProtocol,
    SliceAuditLog,
    TimeSlice,
    PrePeriodBaseline,
    StreamSliceBuilder,
    fit_preperiod_baseline,
    infer_release_cause,
)

__all__ = [
    "TelemetryRecord",
    "SlicingProtocol",
    "SliceAuditLog",
    "TimeSlice",
    "PrePeriodBaseline",
    "StreamSliceBuilder",
    "fit_preperiod_baseline",
    "infer_release_cause",
]
