"""Install-root layout and well-known paths (macOS).

Everything the app owns lives under a single install root so it can be removed
cleanly and so the "keep user data" rules are simple:

    ~/Library/Application Support/mamidlabs/   (default root; MAMIDLABS_ROOT overrides)
        llama.cpp/<build>/llama-server   the pinned llama.cpp build (Metal)
        models/                          GGUF language models (+ mmproj)
        ComfyUI/                         pinned ComfyUI checkout + models/
        venv/{app,imagegen,asr,ocr}/     Python environments (one per concern)
        tools/hf-home/                   Hugging Face cache
        tools/downloads/                 downloaded archives/models
        tools/pip-cache/                 pip cache
        settings/api.json                all user settings (secrets 0600)
        chats/                           chats
        outputs/                         generated files
        logs/                            server/worker logs
        mamidlabs-launch                 launcher (the .app bundle calls this)

Unlike the Windows edition there is no bundled PowerShell: the app runs with
the system Python, so no `runtime/` folder is needed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "mamidlabs"

#: Pinned llama.cpp build (Metal). Must match scripts/install-mamidlabs.sh.
LLAMA_BUILD = "b10998"


def is_macos() -> bool:
    """True on the real target platform (macOS)."""
    return sys.platform == "darwin"


def default_root() -> Path:
    """Return the default install root.

    ``MAMIDLABS_ROOT`` wins when set (used by tests and by installs that want a
    different location). Otherwise follow the macOS convention:
    ``~/Library/Application Support/mamidlabs``. On non-macOS hosts (developer
    machines and CI) fall back to the XDG data directory so the module still
    behaves predictably.
    """
    env = os.environ.get("MAMIDLABS_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    if is_macos():
        return (Path.home() / "Library" / "Application Support" / APP_DIR_NAME).resolve()
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return (base / APP_DIR_NAME).resolve()


class Paths:
    """All app paths derived from one install root."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root).resolve() if root else default_root()

    # --- engine -----------------------------------------------------------------
    @property
    def llama_server(self) -> Path:
        return self.root / "llama.cpp" / LLAMA_BUILD / "llama-server"

    @property
    def comfyui_dir(self) -> Path:
        return self.root / "ComfyUI"

    @property
    def comfyui_main(self) -> Path:
        return self.comfyui_dir / "main.py"

    @property
    def comfyui_models(self) -> Path:
        return self.comfyui_dir / "models"

    # --- python environments ----------------------------------------------------
    def venv(self, name: str) -> Path:
        return self.root / "venv" / name

    def venv_python(self, name: str) -> Path:
        return self.venv(name) / "bin" / "python"

    # --- models -----------------------------------------------------------------
    @property
    def models(self) -> Path:
        return self.root / "models"

    # --- user data --------------------------------------------------------------
    @property
    def settings_dir(self) -> Path:
        return self.root / "settings"

    @property
    def settings_file(self) -> Path:
        return self.settings_dir / "api.json"

    @property
    def chats(self) -> Path:
        return self.root / "chats"

    @property
    def outputs(self) -> Path:
        return self.root / "outputs"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def tools(self) -> Path:
        return self.root / "tools"

    @property
    def hf_home(self) -> Path:
        return self.tools / "hf-home"

    @property
    def downloads(self) -> Path:
        return self.tools / "downloads"

    @property
    def pip_cache(self) -> Path:
        return self.tools / "pip-cache"

    @property
    def rag(self) -> Path:
        """Bound-folder search index (``tools/rag/bound-<hash>.json``)."""
        return self.tools / "rag"

    @property
    def backups(self) -> Path:
        return self.tools / "backup"

    # --- runtime files ----------------------------------------------------------
    @property
    def launch_script(self) -> Path:
        """Shell launcher written by the installer (the .app bundle calls this)."""
        return self.root / "mamidlabs-launch"

    @property
    def server_pid_file(self) -> Path:
        return self.logs / "llama-server.pid"

    @property
    def asr_server_file(self) -> Path:
        return self.logs / "asr-server.json"

    @property
    def audit_log(self) -> Path:
        return self.logs / "audit.jsonl"

    def log_file(self, name: str) -> Path:
        return self.logs / name

    # --- helpers ----------------------------------------------------------------
    def output_dir(self, kind: str) -> Path:
        """``images``, ``videos``, ``documents``, ``charts``, ``refs``, ..."""
        return self.outputs / kind

    def ensure_dirs(self) -> None:
        """Create the folders the app writes to. Never touches models/ComfyUI."""
        for p in (
            self.settings_dir,
            self.chats,
            self.logs,
            self.tools,
            self.hf_home,
            self.downloads,
            self.pip_cache,
            self.rag,
            self.backups,
            self.output_dir("images"),
            self.output_dir("videos"),
            self.output_dir("documents"),
            self.output_dir("charts"),
            self.output_dir("refs"),
            self.output_dir("thumbs"),
            self.output_dir("input"),
        ):
            p.mkdir(parents=True, exist_ok=True)
