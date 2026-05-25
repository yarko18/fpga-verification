# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

import atexit
from importlib.resources import as_file, files
from pathlib import Path
import queue
import subprocess
import threading

import numpy as np
from tqdm import tqdm


class IntelSystemConsoleSession:
    """Persistent System Console session for Avalon-MM and JTAG UART access."""

    def __init__(
        self,
        system_console="system-console",
        master_index=0,
        uart_index=0,
        startup_timeout=30.0,
        work_dir=None,
    ):
        self.system_console = system_console
        self.master_index = int(master_index)
        self.uart_index = int(uart_index)
        self.startup_timeout = float(startup_timeout)
        self.work_dir = Path(work_dir) if work_dir is not None else None

        self._lock = threading.RLock()
        self._proc = None
        self._output = None
        self._reader_thread = None
        self._script_context = None
        self._script_path = None
        atexit.register(self.close)

    def _data_dir(self):
        return self.work_dir if self.work_dir is not None else Path.cwd()

    def _session_script_path(self):
        if self._script_context is None:
            script_resource = files(__package__).joinpath("resources/jtag_session.tcl")
            self._script_context = as_file(script_resource)
            self._script_path = Path(self._script_context.__enter__())

        return self._script_path

    def _release_session_script(self):
        if self._script_context is not None:
            self._script_context.__exit__(None, None, None)
            self._script_context = None
            self._script_path = None

    @staticmethod
    def _stdout_reader(proc, output):
        for line in proc.stdout:
            output.put(line.rstrip("\r\n"))
        output.put(None)

    def _next_line(self, timeout=None):
        try:
            line = self._output.get(timeout=timeout)
        except queue.Empty as exc:
            raise TimeoutError("Timeout waiting for system-console response") from exc

        if line is None:
            ret = self._proc.poll() if self._proc is not None else None
            raise RuntimeError(f"system-console stopped unexpectedly with code {ret}")

        return line

    def _start(self):
        if self._proc is not None and self._proc.poll() is None:
            return
        if self._proc is not None:
            self.close()

        self._output = queue.Queue()
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        cmd = [
            self.system_console,
            "--script",
            str(self._session_script_path()),
            str(self.master_index),
            str(self.uart_index),
        ]

        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=creationflags,
        )
        self._reader_thread = threading.Thread(
            target=self._stdout_reader,
            args=(self._proc, self._output),
            daemon=True,
        )
        self._reader_thread.start()

        try:
            while True:
                line = self._next_line(timeout=self.startup_timeout)
                if line == "JTAG_READY":
                    return
                if line.startswith("JTAG_FATAL\t"):
                    raise RuntimeError(line.split("\t", 1)[1])
        except Exception:
            self.close()
            raise

    def open(self):
        with self._lock:
            self._start()
        return self

    def _send(self, *fields):
        values = [str(field) for field in fields]
        if any("\t" in field or "\r" in field or "\n" in field for field in values):
            raise ValueError("System Console protocol fields must not contain tabs or newlines")

        if self._proc is None or self._proc.poll() is not None:
            raise RuntimeError("system-console session is not running")

        self._proc.stdin.write("\t".join(values) + "\n")
        self._proc.stdin.flush()

    def _transfer(self, operation, fields, total_bytes, desc):
        last_done = 0
        with tqdm(
            total=total_bytes,
            desc=desc,
            unit="B",
            unit_scale=True,
            dynamic_ncols=True,
            leave=True,
        ) as pbar:
            self._send(operation, *fields)

            while True:
                line = self._next_line()
                if line.startswith("PROGRESS_BYTES\t"):
                    _, done, _, _, chunk, addr = line.split("\t")
                    done = int(done)
                    pbar.update(done - last_done)
                    last_done = done
                    pbar.set_postfix_str(f"addr={addr}, chunk={chunk}", refresh=True)
                    continue

                if line == f"JTAG_DONE\t{operation}":
                    return

                if line.startswith("JTAG_ERROR\t"):
                    raise RuntimeError(line)

    def write_memory(self, data, address, chunk_size=4096):
        with self._lock:
            self._start()

            input_file = self._data_dir() / "data_in.bin"
            np.asarray(data).astype("<u2", copy=False).tofile(input_file)
            total_bytes = input_file.stat().st_size

            self._transfer(
                "WRITE",
                (input_file.resolve().as_posix(), hex(address), int(chunk_size)),
                total_bytes,
                "JTAG write",
            )

    def read_memory(self, shape, address, chunk_size=4096):
        with self._lock:
            self._start()

            output_file = self._data_dir() / "data_out.bin"
            total_size_bytes = int(shape[0]) * int(shape[1]) * 2

            self._transfer(
                "READ",
                (
                    output_file.resolve().as_posix(),
                    hex(address),
                    total_size_bytes,
                    int(chunk_size),
                ),
                total_size_bytes,
                "JTAG read",
            )

            data_out = np.fromfile(output_file, dtype="<u2")
            expected_words = int(shape[0]) * int(shape[1])
            if data_out.size != expected_words:
                raise RuntimeError(
                    f"Read size mismatch: got {data_out.size} words, expected {expected_words}"
                )

            return data_out.reshape(shape)

    def command(self, command: str, timeout=3.0, debug=False) -> str:
        if not command:
            raise ValueError("command must not be empty")

        payload_hex = command.encode("utf-8").hex()
        timeout_ms = max(1, int(float(timeout) * 1000))

        with self._lock:
            self._start()
            self._send("UART", payload_hex, timeout_ms)

            while True:
                line = self._next_line(timeout=float(timeout) + 1.0)
                if debug:
                    print("SYSTEM-CONSOLE:", repr(line))

                if line.startswith("UART_RESULT\t"):
                    raw = bytes.fromhex(line.split("\t", 1)[1])
                    response = raw.decode("utf-8", errors="replace")
                    for response_line in response.splitlines():
                        response_line = response_line.strip()
                        if response_line:
                            return response_line
                    raise RuntimeError("Nios returned an empty response")

                if line.startswith("JTAG_ERROR\t"):
                    raise RuntimeError(line)

    # Compatibility aliases for the existing HIL test API.
    write = write_memory
    read = read_memory
    jtag_write = write_memory
    jtag_read = read_memory
    set_get = command

    def close(self):
        with self._lock:
            proc = self._proc
            if proc is not None and proc.poll() is None:
                try:
                    self._send("QUIT")
                    proc.wait(timeout=3.0)
                except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                    proc.terminate()
                    try:
                        proc.wait(timeout=3.0)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()

            self._proc = None
            self._output = None
            self._reader_thread = None
            self._release_session_script()

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


JtagSession = IntelSystemConsoleSession
