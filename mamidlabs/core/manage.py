"""Model lifecycle: start/stop/switch ``llama-server`` by profile.

macOS port of ``scripts/manage-mamidlabs.ps1``. Responsibilities:

* build the per-profile ``llama-server`` argument vector,
* refuse to load a model that will not fit in available memory (the gate),
* keep exactly one managed server on port 8080,
* clean up ComfyUI (idle and duplicate instances) and orphan GPU workers that
  belong to *this* install before loading a model,
* serialise concurrent switches with a file lock (the Windows edition uses a
  named mutex).

Only processes that live under the install root are ever touched.
"""

from __future__ import annotations

import errno
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .paths import Paths
from .profiles import PROFILE_ALIASES, get_profile, model_path, projector_path
from .settings import Settings

PORT = 8080
COMFY_PORT = 8188


class MemoryError_(RuntimeError):
    """Raised when the memory gate refuses to load a model."""


# --- process discovery -------------------------------------------------------
@dataclass(frozen=True)
class Proc:
    pid: int
    ppid: int
    args: str
    exe: str = ""


def list_processes() -> list[Proc]:
    """Enumerate processes via ``ps`` (portable across macOS/Linux/BSD).

    ``-ww`` disables command-line truncation so ``args`` carries the full path
    (root matching depends on it, especially where ``/proc`` is unavailable).
    """
    try:
        out = subprocess.run(
            ["ps", "-ww", "-eo", "pid=,ppid=,args="],
            capture_output=True, text=True, timeout=15, check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    procs: list[Proc] = []
    for line in out.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) < 3:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        procs.append(Proc(pid, ppid, parts[2], _exe_for(pid)))
    return procs


def _exe_for(pid: int) -> str:
    """Resolve a process's executable. Only Linux exposes ``/proc``; elsewhere
    the full command line from ``ps -ww`` is used for root matching."""
    if not sys.platform.startswith("linux"):
        return ""
    try:
        return os.readlink(f"/proc/{pid}/exe")
    except OSError:
        return ""


def _under_root(proc: Proc, root: Path) -> bool:
    root_str = str(root).rstrip("/") + "/"
    return (proc.exe.startswith(root_str)
            or root_str in proc.args
            or proc.args.startswith(str(root)))


def comfy_processes(procs: list[Proc], root: Path) -> list[Proc]:
    return [p for p in procs
            if "ComfyUI" in p.args and "main.py" in p.args and _under_root(p, root)]


def app_gpu_workers(procs: list[Proc], root: Path) -> list[Proc]:
    """Idle ASR/OCR workers owned by this install (not ComfyUI)."""
    out = []
    for p in procs:
        if not _under_root(p, root):
            continue
        if "whisper-tools.py" in p.args or "ocr-tools.py" in p.args:
            out.append(p)
    return out


def _comfy_instance_roots(procs: list[Proc]) -> list[Proc]:
    """ComfyUI is a process *pair* (launcher + child); count by root."""
    ids = {p.pid for p in procs}
    return [p for p in procs if p.ppid not in ids]


def _comfy_under_root(all_procs: list[Proc], pid: int, root_id: int, depth: int = 8) -> bool:
    current = pid
    for _ in range(depth):
        if current == root_id:
            return True
        match = next((p for p in all_procs if p.pid == current), None)
        if not match:
            return False
        current = match.ppid
    return False


def _port_listener_lsof(port: int) -> int | None:
    """PID listening on ``port`` via ``lsof`` (macOS/BSD)."""
    lsof = shutil.which("lsof")
    if not lsof:
        return None
    try:
        out = subprocess.run(
            [lsof, "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True, text=True, timeout=15, check=False,
        ).stdout.split()
        return int(out[0]) if out else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _port_listener(port: int) -> int | None:
    """PID listening on ``port`` (best effort).

    Linux scans ``/proc``; macOS and other systems without ``/proc`` shell out
    to ``lsof``.
    """
    if sys.platform != "linux" or not os.path.isdir("/proc"):
        return _port_listener_lsof(port)
    inodes = set()
    try:
        for line in Path("/proc/net/tcp").read_text().splitlines()[1:]:
            fields = line.split()
            if len(fields) < 10 or fields[3] != "0A":  # 0A = LISTEN
                continue
            local = fields[1]
            if int(local.split(":")[1], 16) == port:
                inodes.add(fields[9])
    except (OSError, ValueError, IndexError):
        return None
    if not inodes:
        return None
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            for fd in (entry / "fd").iterdir():
                try:
                    target = os.readlink(fd)
                except OSError:
                    continue
                if target.startswith("socket:[") and target[8:-1] in inodes:
                    return int(entry.name)
        except OSError:
            continue
    return None


def _kill(pid: int, timeout: float = 15.0) -> bool:
    try:
        os.kill(pid, 15)
    except OSError:
        return False
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return True
        time.sleep(0.2)
    try:
        os.kill(pid, 9)
    except OSError:
        pass
    return True


def stop_idle_comfy(procs: list[Proc], root: Path, port: int = COMFY_PORT) -> bool:
    """Kill every ComfyUI owned by us whose queue is empty."""
    owned = comfy_processes(procs, root)
    if not owned:
        return False
    try:
        import urllib.request

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/queue", timeout=3) as response:
            import json

            queue = json.loads(response.read().decode("utf-8", "replace"))
        if queue.get("queue_running") or queue.get("queue_pending"):
            return False
    except Exception:  # noqa: BLE001 - an unresponsive server is unusable anyway
        pass
    for proc in owned:
        _kill(proc.pid)
    time.sleep(1.5)  # the accelerator releases memory with a small delay
    return True


def stop_comfy_leaks(procs: list[Proc], root: Path, port: int = COMFY_PORT) -> bool:
    """Kill duplicate ComfyUI instances, keeping the one on ``port``."""
    owned = comfy_processes(procs, root)
    if not owned:
        return False
    roots = _comfy_instance_roots(owned)
    if len(roots) <= 1:
        return False
    keep = roots[0].pid
    listener = _port_listener(port)
    if listener:
        for root_proc in roots:
            if _comfy_under_root(owned, listener, root_proc.pid):
                keep = root_proc.pid
                break
    killed = False
    for proc in owned:
        if _comfy_under_root(owned, proc.pid, keep):
            continue
        _kill(proc.pid)
        killed = True
    if killed:
        time.sleep(1.5)
    return killed


def stop_orphan_workers(procs: list[Proc], root: Path) -> bool:
    workers = app_gpu_workers(procs, root)
    if not workers:
        return False
    for proc in workers:
        _kill(proc.pid, timeout=10)
    time.sleep(1.0)
    return True


def managed_servers(procs: list[Proc], server: Path, port: int = PORT) -> list[Proc]:
    server_str = str(server)
    out = []
    for proc in procs:
        if not _under_root(proc, server.parent.parent):
            continue
        if server_str in proc.args and f"--port {port}" in proc.args:
            out.append(proc)
    return out


# --- memory gate -------------------------------------------------------------
def _nvidia_free_mib() -> int | None:
    """Free VRAM of the largest NVIDIA GPU (Linux parity / dev hosts)."""
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None
    try:
        out = subprocess.run(
            [smi, "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15, check=False,
        ).stdout.splitlines()
        if not out:
            return None
        return int("".join(ch for ch in out[0] if ch.isdigit()) or 0)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _sysctl_int(name: str) -> int | None:
    try:
        out = subprocess.run(["sysctl", "-n", name], capture_output=True,
                             text=True, timeout=10, check=False).stdout.strip()
        return int(out) if out.isdigit() else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def macos_total_mib() -> int | None:
    """Total physical (unified) memory on macOS, in MiB."""
    total = _sysctl_int("hw.memsize")
    return total // (1024 * 1024) if total else None


def _macos_available_mib() -> int | None:
    """Reclaimable unified memory (free + inactive + speculative + purgeable).

    macOS keeps a large file cache on purpose, so "Pages free" alone wildly
    understates what a model may claim; the reclaimable pages are the honest
    number, mirroring ``MemAvailable`` on Linux.
    """
    pagesize = _sysctl_int("hw.pagesize") or 4096
    try:
        out = subprocess.run(["vm_stat"], capture_output=True, text=True,
                             timeout=10, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    wanted = ("Pages free", "Pages inactive", "Pages speculative", "Pages purgeable")
    pages = 0
    found = False
    for line in out.splitlines():
        stripped = line.strip()
        for key in wanted:
            if stripped.startswith(key + ":"):
                digits = "".join(ch for ch in stripped.split(":", 1)[-1] if ch.isdigit())
                if digits:
                    pages += int(digits)
                    found = True
    return (pages * pagesize) // (1024 * 1024) if found else None


def available_memory_mib() -> int | None:
    """Memory a model may claim, in MiB, or ``None`` when it cannot be read.

    On macOS the GPU shares the system memory pool, so the gate uses reclaimable
    unified memory (``vm_stat``). On other hosts it prefers the NVIDIA free-VRAM
    query (Linux parity) and finally ``/proc/meminfo``. ``MAMIDLABS_FREE_MEM_MIB``
    overrides the reading (used by tests and for manual tuning).
    """
    override = os.environ.get("MAMIDLABS_FREE_MEM_MIB")
    if override and override.strip().isdigit():
        return int(override.strip())
    if sys.platform == "darwin":
        return _macos_available_mib()
    free = _nvidia_free_mib()
    if free is not None:
        return free
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def memory_budget(model: Path, profile_id: str, projector: Path | None,
                  free_mib: int | None) -> str | None:
    """Return a warning string, raise :class:`MemoryError_`, or return ``None``.

    The projector always runs on the CPU (``--no-mmproj-offload``) so it never
    counts against the model budget. Overhead is 750 MiB for MAX/FLASH and
    300 MiB for LITE; MAX/FLASH tolerance is zero (a model that does not fully
    fit spills out of the GPU/accelerator budget and slows down badly), LITE
    tolerates a small spill.
    """
    if free_mib is None or free_mib <= 0:
        return None
    model_mib = (model.stat().st_size + (1 << 20) - 1) // (1 << 20) if model.exists() else 0
    overhead = 300 if profile_id == "lite" else 750
    needed = model_mib + overhead
    tolerance = 1024 if profile_id == "lite" else 0
    if free_mib < needed - tolerance:
        pool = "unified memory" if sys.platform == "darwin" else "free VRAM"
        raise MemoryError_(
            f"Not enough {pool}: {free_mib} MiB available, the \"{profile_id}\" profile needs an "
            f"estimated minimum of {needed} MiB (model ~{model_mib} MiB, cache/compute headroom "
            f"{overhead} MiB). "
            "Close other applications that use memory (browser, another MamidLabs process, etc.) "
            "and try again, or choose a smaller profile."
        )
    if free_mib < needed:
        return (f"Available memory is about {needed - free_mib} MiB below the estimate; llama.cpp "
                "will keep the large embedding tensor on the CPU (a small speed loss is possible).")
    return None


def gguf_has_mtp(path: Path, probe_bytes: int = 16 * 1024 * 1024) -> bool:
    """True when the GGUF header carries an MTP/``nextn`` block."""
    try:
        with path.open("rb") as handle:
            head = handle.read(probe_bytes)
        return b"nextn" in head
    except OSError:
        return False


# --- argument building -------------------------------------------------------
def server_args(paths: Paths, settings: Settings, profile_id: str,
                model: Path, projector: Path | None, alias: str,
                *, custom: bool = False, mtp: bool | None = None) -> list[str]:
    """Build the ``llama-server`` argument vector for a profile."""
    args = ["--model", str(model), "--alias", alias,
            "--host", "127.0.0.1", "--port", str(PORT)]
    if custom:
        args += ["--ctx-size", "8192", "--predict", "4096", "--parallel", "1",
                 "--gpu-layers", "99", "--flash-attn", "on", "--cache-reuse", "256",
                 "--jinja", "--metrics"]
        if projector:
            args += ["--mmproj", str(projector)]
        return args

    if profile_id == "lite":
        ctx = str(int(settings.get("liteContext", 32768) or 32768))
        args += ["--ctx-size", ctx, "--predict", "8192", "--parallel", "1",
                 "--gpu-layers", "99", "--flash-attn", "on",
                 "--cache-type-k", "q4_0", "--cache-type-v", "q4_0", "--cache-reuse", "256",
                 "--batch-size", "256", "--ubatch-size", "128",
                 "--threads", "4", "--threads-batch", "8",
                 "--jinja", "--reasoning", "on", "--reasoning-effort", "low",
                 "--reasoning-format", "deepseek", "--metrics", "--no-context-shift"]
        if projector:
            args += ["--mmproj", str(projector), "--no-mmproj-offload", "--image-min-tokens", "512"]
    else:
        effort = "xhigh" if profile_id == "max" else "low"
        args += ["--ctx-size", "32768", "--predict", "8192", "--parallel", "1",
                 "--gpu-layers", "99", "--flash-attn", "on",
                 "--cache-type-k", "q4_0", "--cache-type-v", "q4_0", "--cache-reuse", "256",
                 "--batch-size", "512", "--ubatch-size", "256",
                 "--threads", "6", "--threads-batch", "12",
                 "--jinja", "--reasoning", "on", "--reasoning-effort", effort,
                 "--reasoning-format", "deepseek", "--metrics", "--no-context-shift"]
        if projector:
            args = (["--model", str(model), "--mmproj", str(projector),
                     "--no-mmproj-offload", "--image-min-tokens", "1024"]
                    + args[2:])
    # MTP speculative decoding only works when the GGUF actually carries the
    # nextn block; the flag on a model without it makes llama.cpp refuse to start.
    enabled = settings.get("mtp", True) if mtp is None else mtp
    if enabled and gguf_has_mtp(model):
        args += ["--spec-type", "draft-mtp"]
    return args


# --- file lock ---------------------------------------------------------------
def _lock_exclusive(handle) -> bool:
    """Try to take an exclusive advisory lock; return False if held elsewhere."""
    try:
        import fcntl  # POSIX (the real target platform)

        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                return False
            raise
    except ImportError:  # pragma: no cover - Windows dev/test host
        import msvcrt

        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False


def _unlock(handle) -> None:
    try:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except ImportError:  # pragma: no cover - Windows dev/test host
        import msvcrt

        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass


class FileLock:
    """Advisory exclusive lock on a file (stand-in for the Windows mutex)."""

    def __init__(self, path: Path, timeout: float = 30.0) -> None:
        self.path = path
        self.timeout = timeout
        self._handle = None

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("w")
        deadline = time.time() + self.timeout
        while not _lock_exclusive(self._handle):
            if time.time() >= deadline:
                self._handle.close()
                self._handle = None
                raise TimeoutError("Model control is in use by another process.")
            time.sleep(0.2)
        return self

    def __exit__(self, *exc: object) -> None:
        if self._handle is not None:
            _unlock(self._handle)
            self._handle.close()
            self._handle = None


# --- manager -----------------------------------------------------------------
class ModelManager:
    def __init__(self, paths: Paths, settings: Settings,
                 process_lister=list_processes, free_mib=available_memory_mib) -> None:
        self.paths = paths
        self.settings = settings
        self._list_processes = process_lister
        self._free_mib = free_mib

    @property
    def lock_path(self) -> Path:
        return self.paths.logs / "model-control.lock"

    def _server(self) -> Path:
        return self.paths.llama_server

    def active_alias(self) -> str | None:
        procs = managed_servers(self._list_processes(), self._server())
        if len(procs) != 1:
            return None
        args = procs[0].args
        for alias in PROFILE_ALIASES.values():
            if f"--alias {alias}" in args:
                return alias
        return None

    def start(self, profile_id: str, *, model_id: str | None = None,
              skip_memory_check: bool = False) -> str:
        """Start (or switch to) a profile. Returns a human-readable status line."""
        profile = get_profile(profile_id)
        custom_model = self._custom_model(model_id)
        if custom_model:
            model = Path(custom_model["path"])
            alias = str(custom_model.get("id") or profile.alias)
            projector = next(iter(Path(model).parent.glob("*mmproj*.gguf")), None)
            custom = True
        else:
            model = model_path(self.paths, profile_id)
            projector = projector_path(self.paths, profile_id)
            alias = profile.alias
            custom = False

        with FileLock(self.lock_path):
            running = managed_servers(self._list_processes(), self._server())
            if running and f"--alias {alias}" in running[0].args and len(running) == 1:
                return f"Already loaded: {alias} (PID {running[0].pid})"
            self._stop_servers(running)

            if not self._server().exists():
                raise FileNotFoundError(f"llama-server not found: {self._server()}")
            if not model.exists():
                raise FileNotFoundError(f"Model not found: {model}")
            if not custom and profile_id != "lite" and projector and not projector.exists():
                raise FileNotFoundError(f"Vision projector not found: {projector}")

            self._cleanup_before_load(profile_id, skip_memory_check)
            args = server_args(self.paths, self.settings, profile_id, model, projector,
                               alias, custom=custom)

            self.paths.logs.mkdir(parents=True, exist_ok=True)
            out = (self.paths.logs / f"mamidlabs-{profile_id}.stdout.log").open("ab")
            err = (self.paths.logs / f"mamidlabs-{profile_id}.stderr.log").open("ab")
            try:
                child = subprocess.Popen(  # noqa: S603
                    [str(self._server()), *args],
                    stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                    start_new_session=True, cwd=str(self._server().parent),
                )
            finally:
                out.close()
                err.close()
            self.paths.server_pid_file.write_text(str(child.pid), encoding="utf-8")
            return f"Loading: {alias} (PID {child.pid})"

    def stop(self) -> str:
        with FileLock(self.lock_path):
            running = managed_servers(self._list_processes(), self._server())
            self._stop_servers(running)
        return "Model stopped."

    def close_comfy(self) -> str:
        with FileLock(self.lock_path):
            stop_idle_comfy(self._list_processes(), self.paths.root)
        return "ComfyUI closed (if the queue was empty)."

    # --- internals -----------------------------------------------------------
    def _custom_model(self, model_id: str | None) -> dict | None:
        selected = model_id or str(self.settings.get("selectedLocalModel") or "")
        if not selected or selected.startswith("builtin-"):
            return None
        for entry in self.settings.get("localModels", []):
            if entry.get("id") == selected:
                return entry
        raise FileNotFoundError("The registered local model was not found.")

    def _stop_servers(self, running: list[Proc]) -> None:
        for proc in running:
            _kill(proc.pid, timeout=20)
        if running:
            deadline = time.time() + 20
            while managed_servers(self._list_processes(), self._server()) and time.time() < deadline:
                time.sleep(0.25)
            if managed_servers(self._list_processes(), self._server()):
                raise RuntimeError("The previous model process did not exit.")
            time.sleep(0.5)

    def _cleanup_before_load(self, profile_id: str, skip_memory_check: bool) -> None:
        procs = self._list_processes()
        stop_comfy_leaks(procs, self.paths.root)
        keep_alive = bool(self.settings.get("comfyKeepAlive", False))
        if not keep_alive or profile_id != "lite":
            stop_idle_comfy(self._list_processes(), self.paths.root)
        stop_orphan_workers(self._list_processes(), self.paths.root)
        if skip_memory_check:
            return
        model = model_path(self.paths, profile_id)
        last_error: Exception | None = None
        for attempt in range(8):
            try:
                warning = memory_budget(model, profile_id,
                                        projector_path(self.paths, profile_id),
                                        self._free_mib())
                if warning:
                    print(f"WARNING: {warning}")
                return
            except MemoryError_ as exc:
                last_error = exc
                if attempt == 0 and stop_idle_comfy(self._list_processes(), self.paths.root):
                    continue
                if attempt < 7:
                    time.sleep(1.0)
        if last_error:
            raise last_error
