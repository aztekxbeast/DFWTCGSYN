"""Manage the PokeHunt Discord bot as a supervised child process."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Deque, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
BOT_SCRIPT = PROJECT_ROOT / "bot.py"
LOG_RING_SIZE = 2000

LOGIN_FAILURE_PATTERNS = (
    re.compile(r"improper token", re.I),
    re.compile(r"invalid.?token", re.I),
    re.compile(r"login.?failure", re.I),
    re.compile(r"401", re.I),
    re.compile(r"unauthorized", re.I),
)

READY_PATTERN = re.compile(r"logged in as|bot is ready|on_ready", re.I)


@dataclass
class LogLine:
    stream: str  # "out" | "err" | "sys"
    text: str
    ts: float = field(default_factory=time.time)


class BotManager:
    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._reader_threads: list[threading.Thread] = []
        self._log_lock = threading.Lock()
        self._logs: Deque[LogLine] = deque(maxlen=LOG_RING_SIZE)
        self._listeners: list[Callable[[str], None]] = []
        self._status = "stopped"  # stopped | starting | running | failed | stopping
        self._last_error: Optional[str] = None
        self._watchdog: Optional[threading.Thread] = None

    # ── events ────────────────────────────────────────────────────────────

    def add_listener(self, cb: Callable[[str], None]) -> None:
        self._listeners.append(cb)

    def _emit(self, event: str) -> None:
        for cb in list(self._listeners):
            try:
                cb(event)
            except Exception:
                pass

    def _append(self, stream: str, text: str) -> None:
        line = LogLine(stream=stream, text=text.rstrip("\n"))
        with self._log_lock:
            self._logs.append(line)
        self._emit("log")

    # ── status ────────────────────────────────────────────────────────────

    @property
    def status(self) -> str:
        return self._status

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def get_logs(self, limit: int = 200) -> list[LogLine]:
        with self._log_lock:
            return list(self._logs)[-limit:]

    def clear_logs(self) -> None:
        with self._log_lock:
            self._logs.clear()
        self._emit("log")

    # ── process control ───────────────────────────────────────────────────

    def resolve_python(self) -> Path:
        if VENV_PYTHON.exists():
            return VENV_PYTHON
        # Fall back to whatever launched the GUI
        return Path(sys.executable)

    def bot_deps_installed(self) -> bool:
        py = self.resolve_python()
        result = subprocess.run(
            [str(py), "-c", "import discord, aiosqlite, dotenv, aiohttp"],
            capture_output=True,
            cwd=str(PROJECT_ROOT),
        )
        return result.returncode == 0

    def start(self, env_overrides: Optional[dict[str, str]] = None) -> bool:
        if self.is_running():
            return True
        if not BOT_SCRIPT.exists():
            self._last_error = f"bot.py not found at {BOT_SCRIPT}"
            self._status = "failed"
            self._append("sys", f"ERROR: {self._last_error}")
            self._emit("status")
            return False

        py = self.resolve_python()
        if not self.bot_deps_installed():
            self._last_error = "Bot dependencies missing. Install with: .venv/bin/pip install -r requirements.txt"
            self._status = "failed"
            self._append("sys", f"ERROR: {self._last_error}")
            self._emit("status")
            return False

        env = os.environ.copy()
        # Prefer project .env written by credentials store; also inject overrides
        env.setdefault("PYTHONUNBUFFERED", "1")
        env["PYTHONUNBUFFERED"] = "1"
        if env_overrides:
            env.update(env_overrides)

        (PROJECT_ROOT / "data").mkdir(exist_ok=True)

        self._status = "starting"
        self._last_error = None
        self._emit("status")
        self._append("sys", f"Starting bot with {py.name} …")

        try:
            self._proc = subprocess.Popen(
                [str(py), "-u", str(BOT_SCRIPT)],
                cwd=str(PROJECT_ROOT),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,  # survive GUI signals; we still manage lifetime
            )
        except OSError as exc:
            self._status = "failed"
            self._last_error = str(exc)
            self._append("sys", f"ERROR: failed to spawn bot: {exc}")
            self._emit("status")
            return False

        t = threading.Thread(target=self._read_output, args=(self._proc,), daemon=True)
        t.start()
        self._reader_threads.append(t)

        self._watchdog = threading.Thread(target=self._watch, args=(self._proc,), daemon=True)
        self._watchdog.start()
        return True

    def _read_output(self, proc: subprocess.Popen) -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            self._append("out", line)
            if READY_PATTERN.search(line) and self._status in ("starting", "running"):
                if self._status != "running":
                    self._status = "running"
                    self._emit("status")
            for pat in LOGIN_FAILURE_PATTERNS:
                if pat.search(line):
                    self._last_error = "Discord login failed — check the bot token in Setup."
                    self._append("sys", "LOGIN FAILED: token rejected by Discord.")
                    self._emit("status")
                    break
        try:
            proc.stdout.close()
        except Exception:
            pass

    def _watch(self, proc: subprocess.Popen) -> None:
        code = proc.wait()
        if self._proc is proc:
            self._proc = None
            if self._status == "stopping":
                self._status = "stopped"
                self._append("sys", "Bot stopped.")
            elif code == 0:
                self._status = "stopped"
                self._append("sys", "Bot exited cleanly.")
            else:
                self._status = "failed"
                if not self._last_error:
                    self._last_error = f"Bot exited with code {code}."
                self._append("sys", f"Bot exited with code {code}.")
            self._emit("status")

    def stop(self, timeout: float = 8.0) -> None:
        if not self.is_running() or self._proc is None:
            self._status = "stopped"
            self._emit("status")
            return
        self._status = "stopping"
        self._emit("status")
        self._append("sys", "Stopping bot …")
        proc = self._proc
        try:
            # Interrupt the process group so asyncio tasks shut down
            os.killpg(os.getpgid(proc.pid), signal.SIGINT)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.send_signal(signal.SIGINT)
            except Exception:
                pass
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._append("sys", "Force-killing bot …")
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                proc.kill()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass

    def restart(self, env_overrides: Optional[dict[str, str]] = None) -> bool:
        self.stop()
        # Small pause so Discord gateway can release the session
        time.sleep(1.0)
        return self.start(env_overrides=env_overrides)
