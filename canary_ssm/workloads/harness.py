"""Disposable Isolated Worker Harness.

Provides sandboxed subprocess execution with:
- Dedicated process group containment (CREATE_NEW_PROCESS_GROUP on Windows)
- Ephemeral temporary working directory
- Loopback-only network binding on dynamic ephemeral port
- Resource watchdog enforcing RSS memory limits and execution timeouts
- Deterministic teardown and recursive process harvesting (no zombie processes)
- Complete isolation from simulator truth and detector state
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError

import psutil

from .models import HarnessFailureType, WorkerLimits


class IsolatedWorkerHarness:
    """Manages the lifecycle and isolation boundary of a disposable worker process."""

    def __init__(
        self,
        script_path: Path | str,
        limits: WorkerLimits | None = None,
        server_id: str = "srv-0",
        service_name: str = "worker",
    ) -> None:
        self.script_path = Path(script_path).resolve()
        if not self.script_path.exists():
            raise FileNotFoundError(f"Worker script does not exist: {self.script_path}")

        self.limits = limits or WorkerLimits()
        self.server_id = server_id
        self.service_name = service_name

        self.process: subprocess.Popen | None = None
        self.psutil_proc: psutil.Process | None = None
        self.temp_dir: tempfile.TemporaryDirectory | None = None
        self.port: int | None = None
        self.start_time: float = 0.0
        self.peak_memory_mb: float = 0.0
        self.harness_failure: HarnessFailureType | None = None
        self.exit_code: int | None = None
        self.error_details: str | None = None

        self._stop_event = threading.Event()
        self._watchdog_thread: threading.Thread | None = None

    def __enter__(self) -> "IsolatedWorkerHarness":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()

    def start(self) -> None:
        """Start the worker subprocess inside an isolated disposable environment."""
        if self.process is not None:
            raise RuntimeError("Worker process is already running")

        # 1. Ephemeral scratch directory
        self.temp_dir = tempfile.TemporaryDirectory(prefix="worker_sandbox_")

        # 2. Sanitized environment (zero truth tokens or leaking paths)
        clean_env = {
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"),
            "PATH": os.environ.get("PATH", ""),
            "PYTHONUNBUFFERED": "1",
            "TEMP": self.temp_dir.name,
            "TMP": self.temp_dir.name,
        }

        # 3. Process flags (separate process group for clean kill)
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        cmd = [
            sys.executable,
            "-u",  # unbuffered stdout/stderr
            str(self.script_path),
            "--host",
            "127.0.0.1",
            "--port",
            "0",
        ]

        try:
            self.start_time = time.perf_counter()
            self.process = subprocess.Popen(
                cmd,
                cwd=self.temp_dir.name,
                env=clean_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
                text=True,
            )
            self.psutil_proc = psutil.Process(self.process.pid)
        except Exception as exc:
            self.harness_failure = HarnessFailureType.HARNESS_STARTUP_FAILURE
            self.error_details = f"Failed to spawn worker subprocess: {exc}"
            self._cleanup_temp_dir()
            raise RuntimeError(self.error_details) from exc

        # 4. Synchronize startup: discover dynamic port
        self._wait_for_startup()

        # 5. Start background resource and timeout watchdog
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop,
            name=f"WorkerWatchdog-{self.server_id}",
            daemon=True,
        )
        self._watchdog_thread.start()

    def _wait_for_startup(self) -> None:
        """Read the dynamic bound port from the worker process stdout and verify /health."""
        deadline = time.perf_counter() + self.limits.startup_timeout_seconds
        discovered_port: int | None = None

        while time.perf_counter() < deadline:
            if self.process.poll() is not None:
                # Process exited prematurely
                _, stderr_data = self.process.communicate(timeout=1.0)
                self.harness_failure = HarnessFailureType.HARNESS_STARTUP_FAILURE
                self.exit_code = self.process.returncode
                self.error_details = f"Worker died on startup with exit code {self.exit_code}: {stderr_data.strip()}"
                self.stop()
                raise RuntimeError(self.error_details)

            line = self.process.stdout.readline().strip()
            if line.startswith("LISTENING "):
                try:
                    discovered_port = int(line.split()[1])
                    break
                except (IndexError, ValueError) as err:
                    self.harness_failure = HarnessFailureType.HARNESS_STARTUP_FAILURE
                    self.error_details = f"Malformed startup line: {line!r}"
                    self.stop()
                    raise RuntimeError(self.error_details) from err
            time.sleep(0.01)

        if discovered_port is None:
            self.harness_failure = HarnessFailureType.HARNESS_STARTUP_FAILURE
            self.error_details = (
                f"Worker failed to signal LISTENING port within {self.limits.startup_timeout_seconds}s"
            )
            self.stop()
            raise TimeoutError(self.error_details)

        self.port = discovered_port

        # Probe /health endpoint
        health_url = f"http://127.0.0.1:{self.port}/health"
        health_ok = False
        while time.perf_counter() < deadline:
            try:
                req = Request(health_url)
                with urlopen(req, timeout=1.0) as resp:
                    if resp.status == 200:
                        health_ok = True
                        break
            except Exception:
                time.sleep(0.02)

        if not health_ok:
            self.harness_failure = HarnessFailureType.HARNESS_STARTUP_FAILURE
            self.error_details = f"Worker failed health check probe at {health_url}"
            self.stop()
            raise RuntimeError(self.error_details)

    def _watchdog_loop(self) -> None:
        """Background monitoring thread enforcing memory and execution limits."""
        while not self._stop_event.is_set():
            if self.process is None or self.process.poll() is not None:
                break

            # 1. Check execution timeout
            elapsed = time.perf_counter() - self.start_time
            if elapsed > self.limits.timeout_seconds:
                self.harness_failure = HarnessFailureType.HARNESS_TIMEOUT
                self.error_details = (
                    f"Execution exceeded timeout limit of {self.limits.timeout_seconds}s (elapsed: {elapsed:.2f}s)"
                )
                self._force_kill()
                break

            # 2. Check RSS memory limit
            try:
                if self.psutil_proc and self.psutil_proc.is_running():
                    mem_info = self.psutil_proc.memory_info()
                    rss_mb = mem_info.rss / (1024.0 * 1024.0)
                    if rss_mb > self.peak_memory_mb:
                        self.peak_memory_mb = rss_mb

                    if rss_mb > self.limits.max_memory_mb:
                        self.harness_failure = HarnessFailureType.HARNESS_OOM_KILLED
                        self.error_details = (
                            f"Worker RSS memory ({rss_mb:.1f} MB) exceeded limit of {self.limits.max_memory_mb:.1f} MB"
                        )
                        self._force_kill()
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break

            self._stop_event.wait(self.limits.poll_interval_seconds)

    def _force_kill(self) -> None:
        """Immediately terminate the worker and all its child processes."""
        if self.process is None:
            return

        try:
            if self.psutil_proc and self.psutil_proc.is_running():
                # Harvest child processes
                children = self.psutil_proc.children(recursive=True)
                for child in children:
                    try:
                        child.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

                self.psutil_proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        try:
            self.process.kill()
        except OSError:
            pass

    def stop(self) -> None:
        """Gracefully stop the worker, falling back to forced recursive kill and cleanup."""
        self._stop_event.set()

        if self._watchdog_thread and self._watchdog_thread.is_alive():
            self._watchdog_thread.join(timeout=1.0)

        if self.process is not None:
            # Attempt graceful HTTP shutdown if still alive and no harness failure
            if self.process.poll() is None and self.port is not None and self.harness_failure is None:
                try:
                    shutdown_url = f"http://127.0.0.1:{self.port}/shutdown"
                    req = Request(shutdown_url, data=b"", method="POST")
                    with urlopen(req, timeout=0.5):
                        pass
                except Exception:
                    pass

            # Wait briefly for graceful exit
            try:
                self.process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                # Force kill if still lingering
                self._force_kill()
                try:
                    self.process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    pass

            self.exit_code = self.process.poll()
            if self.exit_code is not None and self.exit_code != 0 and self.harness_failure is None:
                self.harness_failure = HarnessFailureType.HARNESS_CRASH
                self.error_details = f"Worker exited unexpectedly with status code {self.exit_code}"

            self.process = None
            self.psutil_proc = None

        self._cleanup_temp_dir()

    def _cleanup_temp_dir(self) -> None:
        """Safely delete the ephemeral temporary working directory."""
        if self.temp_dir is not None:
            try:
                self.temp_dir.cleanup()
            except Exception:
                pass
            self.temp_dir = None

    def get_current_metrics(self) -> dict[str, Any]:
        """Query real-time physical metrics from the live worker process."""
        if self.process is None or self.process.poll() is not None:
            return {"alive": False, "memory_mb": 0.0, "cpu_fraction": 0.0}

        try:
            if self.psutil_proc and self.psutil_proc.is_running():
                mem_mb = self.psutil_proc.memory_info().rss / (1024.0 * 1024.0)
                cpu = self.psutil_proc.cpu_percent(interval=None) / 100.0
                if mem_mb > self.peak_memory_mb:
                    self.peak_memory_mb = mem_mb
                return {"alive": True, "memory_mb": mem_mb, "cpu_fraction": min(max(cpu, 0.0), 1.0)}
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        return {"alive": False, "memory_mb": 0.0, "cpu_fraction": 0.0}

    def is_alive(self) -> bool:
        """Check whether the worker process is currently running."""
        return self.process is not None and self.process.poll() is None
