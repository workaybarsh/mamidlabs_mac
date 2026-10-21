"""Run the JSON stdin/stdout worker scripts.

The workers keep the one-shot contract from the Windows edition: one JSON
request on stdin, one JSON response on stdout, executed by the Python of the
venv that owns the relevant dependencies (``app``, ``imagegen``, ``asr``,
``ocr``). Every child gets ``MAMIDLABS_ROOT`` and ``HF_HOME`` so it can find the
install root and the offline model cache without deriving them from its own
location.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from .paths import Paths
from .settings import Settings

#: Worker scripts live next to the package (shipped inside the wheel/venv).
WORKERS_DIR = Path(__file__).resolve().parent.parent / "workers"

DEFAULT_TIMEOUT = 180.0


class WorkerError(RuntimeError):
    pass


class WorkerRunner:
    def __init__(self, paths: Paths, settings: Settings,
                 workers_dir: Path | None = None) -> None:
        self.paths = paths
        self.settings = settings
        self.workers_dir = workers_dir or WORKERS_DIR

    def script(self, name: str) -> Path:
        return self.workers_dir / name

    def python(self, env_name: str = "app") -> Path:
        """Python of a venv, falling back to the running interpreter."""
        candidate = self.paths.venv_python(env_name)
        return candidate if candidate.exists() else Path(sys.executable)

    def child_env(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        env = dict(os.environ)
        env["MAMIDLABS_ROOT"] = str(self.paths.root)
        env.setdefault("HF_HOME", str(self.paths.hf_home))
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")
        if extra:
            env.update(extra)
        return env

    def run(self, script: str | Path, payload: dict, *, env_name: str = "app",
            timeout: float = DEFAULT_TIMEOUT,
            extra_env: dict[str, str] | None = None) -> dict:
        """Run one worker request and return the parsed JSON response."""
        path = Path(script)
        if not path.is_absolute():
            path = self.script(str(script))
        if not path.exists():
            return {"error": f"worker not found: {path}"}
        try:
            completed = subprocess.run(  # noqa: S603
                [str(self.python(env_name)), str(path)],
                input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                capture_output=True, timeout=timeout,
                env=self.child_env(extra_env), cwd=str(self.paths.root),
            )
        except subprocess.TimeoutExpired:
            return {"error": f"worker timed out ({timeout:.0f} s): {path.name}"}
        except OSError as exc:
            return {"error": f"worker could not be started: {exc}"}
        stdout = completed.stdout.decode("utf-8", errors="replace").strip()
        if not stdout:
            stderr = completed.stderr.decode("utf-8", errors="replace").strip()
            return {"error": f"worker produced no output: {stderr[:400] or 'no output'}"}
        # The last non-empty line is the response (workers may log before it).
        line = stdout.splitlines()[-1]
        try:
            return json.loads(line)
        except ValueError:
            return {"error": f"worker returned invalid JSON: {line[:400]}"}
