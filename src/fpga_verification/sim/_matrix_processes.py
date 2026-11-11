# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Cross-platform lifecycle management for matrix child-process trees."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time

_TERMINATE_TIMEOUT_SECONDS = 5.0


def process_group_options() -> dict[str, object]:
    """Return ``Popen`` options that isolate one simulation process tree."""
    if os.name == "nt":
        return {
            "creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        }
    return {"start_new_session": True}


def _is_running(process: subprocess.Popen) -> bool:
    try:
        return process.poll() is None
    except OSError:
        return False


def _request_process_tree_stop(process: subprocess.Popen) -> None:
    if not _is_running(process):
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=_TERMINATE_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
            except OSError:
                pass
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except OSError:
        try:
            process.terminate()
        except OSError:
            pass


def _force_process_tree_stop(process: subprocess.Popen) -> None:
    if not _is_running(process):
        return
    if os.name == "nt":
        try:
            process.kill()
        except OSError:
            pass
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        try:
            process.kill()
        except OSError:
            pass


def _terminate_processes(processes: tuple[subprocess.Popen, ...]) -> None:
    for process in processes:
        _request_process_tree_stop(process)

    deadline = time.monotonic() + _TERMINATE_TIMEOUT_SECONDS
    for process in processes:
        if not _is_running(process):
            continue
        try:
            process.wait(timeout=max(0.0, deadline - time.monotonic()))
        except (OSError, subprocess.TimeoutExpired):
            pass

    running = tuple(process for process in processes if _is_running(process))
    for process in running:
        _force_process_tree_stop(process)
    for process in running:
        try:
            process.wait(timeout=1.0)
        except (OSError, subprocess.TimeoutExpired):
            pass


class ProcessRegistry:
    """Track active simulation process groups shared by matrix workers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._processes: set[subprocess.Popen] = set()
        self._stopping = False

    @property
    def stopping(self) -> bool:
        with self._lock:
            return self._stopping

    def register(self, process: subprocess.Popen) -> None:
        with self._lock:
            stop_immediately = self._stopping
            if not stop_immediately:
                self._processes.add(process)
        if stop_immediately:
            _terminate_processes((process,))

    def unregister(self, process: subprocess.Popen) -> None:
        with self._lock:
            self._processes.discard(process)

    def terminate(self, process: subprocess.Popen) -> None:
        """Terminate one failed worker's process tree without stopping others."""
        _terminate_processes((process,))

    def terminate_all(self) -> None:
        """Prevent new launches and terminate every registered process tree."""
        with self._lock:
            self._stopping = True
            processes = tuple(self._processes)
        _terminate_processes(processes)
        with self._lock:
            self._processes.difference_update(processes)
