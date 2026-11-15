"""Tiny resource-world fixtures; all figures and gates consume saved CSV rows."""
from pathlib import Path
import json

import pandas as pd

from .engine import SimulationEngine, load_engine_config


def _plot(hosts, services, output, name):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    h = pd.read_csv(hosts).groupby("simulated_seconds").mean(numeric_only=True)
    s = pd.read_csv(services).groupby("simulated_seconds").sum(numeric_only=True)
    fig, axes = plt.subplots(5, 1, figsize=(11, 12), sharex=True, constrained_layout=True)
    fig.suptitle(f"Synthetic resource world — {name.replace('_', ' ')}", fontsize=16)
    axes[0].plot(s.index, s.arrivals, label="Arrivals/tick")
    axes[0].plot(s.index, s.completed, label="Completed/tick")
    drops = s[[c for c in s.columns if c.startswith("dropped_")]].sum(axis=1)
    axes[0].plot(s.index, drops, label="Dropped/tick")
    axes[0].set_ylabel("Requests per tick")
    axes[1].plot(h.index, 100 * h.cpu_utilization, label="Mean host CPU")
    axes[1].set_ylabel("CPU (%)")
    for column, label in (("memory_baseline_mb", "Baseline"), ("memory_temporary_mb", "Temporary, end tick"),
                          ("memory_retained_mb", "Retained"), ("memory_peak_mb", "Total, peak tick")):
        axes[2].plot(h.index, h[column], label=label)
    axes[2].set_ylabel("Mean host memory (MB)")
    axes[3].plot(h.index, h.queue_end, label="Mean host queue")
    axes[3].set_ylabel("Queued requests")
    axes[4].plot(h.index, h.latency_proxy_ms, label="Queue/service latency proxy (not p95)")
    axes[4].set_ylabel("Estimated latency (ms)")
    axes[4].set_xlabel("Simulated seconds")
    for ax in axes:
        ax.grid(alpha=0.2)
        ax.legend(loc="upper right", fontsize=8)
    fig.savefig(output, dpi=140)
    plt.close(fig)


def run_fixtures(out: Path):
    out = Path(out)
    root = Path(__file__).resolve().parents[1]
    summaries = []
    bounds, conservation, replay = True, True, True
    for name in ("low_load", "increased_load", "recovery"):
        engine = SimulationEngine(load_engine_config(root / "configs" / f"world_{name}.yaml"))
        engine.start()
        engine.advance(120)
        engine.pause()
        directory = out / name
        engine.export_traces(directory)
        engine.save(directory / "run.json")
        replay &= SimulationEngine.replay(json.loads((directory / "run.json").read_text())).artifact() == engine.artifact()
        h = pd.read_csv(directory / "hosts.csv")
        s = pd.read_csv(directory / "services.csv")
        bounds &= bool((h.cpu_utilization.between(0, 1)).all() and (h.memory_mb <= h.memory_capacity_mb).all()
                       and (h.memory_peak_mb <= h.memory_capacity_mb).all() and h.queue_end.between(0, 300).all())
        conservation &= bool((s.arrivals == s.accepted + s.dropped_queue + s.dropped_memory +
                              s.dropped_unavailable_routes + s.dropped_arrival_limit).all() and
                             (s.queue_start + s.accepted == s.queue_end + s.completed + s.dropped_unavailable_queued).all())
        for start, end, phase in ((1, 20, "initial"), (21, 60, "middle"), (91, 120, "final")):
            hp = h[h.tick.between(start, end)]
            sp = s[s.tick.between(start, end)]
            summaries.append({"scenario": name, "phase": phase, "cpu_mean": hp.cpu_utilization.mean(),
                "memory_mean_mb": hp.memory_mb.mean(), "queue_mean": hp.queue_end.mean(),
                "latency_proxy_mean_ms": hp.latency_proxy_ms.mean(),
                "dropped": int(sp[[c for c in sp.columns if c.startswith('dropped_')]].sum().sum()),
                "completed": int(sp.completed.sum())})
        _plot(directory / "hosts.csv", directory / "services.csv", directory / "traces.png", name)
    table = pd.DataFrame(summaries)
    table.to_csv(out / "summary.csv", index=False)
    # Gate uses the saved table, never hard-coded simulation outputs.
    saved = pd.read_csv(out / "summary.csv").set_index(["scenario", "phase"])
    low, high, recovered = saved.loc[("low_load", "middle")], saved.loc[("increased_load", "middle")], saved.loc[("recovery", "final")]
    gate = {"bounds": bool(bounds), "request_conservation": bool(conservation), "replay": bool(replay),
            "load_raises_cpu": bool(high.cpu_mean > low.cpu_mean),
            "load_raises_memory": bool(high.memory_mean_mb > low.memory_mean_mb),
            "load_raises_queue_and_latency": bool(high.queue_mean > low.queue_mean and high.latency_proxy_mean_ms > low.latency_proxy_mean_ms),
            "overload_drops_reported": bool(high.dropped > 0),
            "recovery_drains_queue": bool(recovered.queue_mean == 0 and recovered.latency_proxy_mean_ms < high.latency_proxy_mean_ms)}
    result = {"generator_id": "world-resources-v1", "synthetic": True,
              "checks": gate, "passed": all(gate.values()), "ticks_per_scenario": 120}
    (out / "fixture_checks.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
