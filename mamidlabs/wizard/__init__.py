"""The setup wizard (``python -m mamidlabs.wizard``).

This package is split so the *logic* stays testable without Qt:

* this module holds the pure helpers — locating the installer script, building
  its argument list, and parsing the progress file. Importing it never pulls in
  PySide6;
* :mod:`mamidlabs.wizard.setup` is the Qt window (``QWizard``) and is imported
  lazily by :mod:`mamidlabs.wizard.__main__`.

The wizard is *not* the installer. It collects the user's choices, writes them
into ``settings/api.json`` (language, own model paths, first-run API flag) and
runs ``scripts/install-mamidlabs.sh`` with the matching flags, showing progress.
Everything the installer does can still be done from the terminal.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

#: Profile ids the wizard can pass to the installer.
INSTALL_PROFILES = ("lite", "flash")

#: Every choice the profile page offers, in display order.
PROFILE_CHOICES = ("lite", "flash", "later", "own")


def repo_root() -> Path:
    """The repository (or installed program) root, from the package location.

    ``mamidlabs/wizard/__init__.py`` → three levels up is the root that holds
    ``scripts/`` and ``EULA.txt``.
    """
    return Path(__file__).resolve().parents[2]


def find_install_script() -> Path | None:
    """Locate ``install-mamidlabs.sh``.

    Honours ``MAMIDLABS_INSTALL_SCRIPT``, then the in-tree script, then the
    conventional system locations used by the ``.deb``/AppImage layout.
    """
    candidates: list[Path] = []
    override = os.environ.get("MAMIDLABS_INSTALL_SCRIPT")
    if override:
        candidates.append(Path(override))
    candidates.append(repo_root() / "scripts" / "install-mamidlabs.sh")
    candidates.append(Path("/usr/share/mamidlabs/scripts/install-mamidlabs.sh"))
    candidates.append(Path("/opt/mamidlabs/scripts/install-mamidlabs.sh"))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def find_eula() -> Path | None:
    """Locate ``EULA.txt`` (shown on the licence page)."""
    candidates = [
        repo_root() / "EULA.txt",
        Path("/usr/share/mamidlabs/EULA.txt"),
        Path("/usr/share/doc/mamidlabs/EULA.txt"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def build_install_args(root: Path | str, profile: str | None, language: str, *,
                       download_models: bool = True, media: bool = True,
                       audio: bool = True, ocr: bool = True) -> list[str]:
    """Argument list for ``install-mamidlabs.sh`` (without the script itself).

    ``profile`` is one of :data:`INSTALL_PROFILES`, or ``None`` when the user
    chose not to download models. ``--skip-*`` flags are added for every
    component the user unchecked so the installer never has to guess.
    """
    args = ["--root", str(root), "--language", language]
    if download_models and profile in INSTALL_PROFILES:
        args += ["--profile", profile]
    else:
        args.append("--skip-models")
    if not media:
        args.append("--skip-media")
    if not audio:
        args.append("--skip-audio")
    if not ocr:
        args.append("--skip-ocr")
    return args


def build_smoke_args(root: Path | str, profile: str | None) -> list[str]:
    """Argument list for ``smoke-test.sh`` (empty when no local profile)."""
    args = ["--root", str(root)]
    if profile in INSTALL_PROFILES:
        args += ["--profile", profile]
    return args


def parse_progress(text: str) -> tuple[int, int, str]:
    """Parse ``logs/kurulum-adim.txt`` (three lines: index, total, step name).

    Returns ``(0, 0, "")`` when the file is absent, empty or malformed — the
    wizard then just shows a busy indicator instead of a percentage.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        return 0, 0, ""
    try:
        index, total = int(lines[0]), int(lines[1])
    except ValueError:
        return 0, 0, ""
    if index <= 0 or total <= 0:
        return 0, 0, ""
    return index, total, lines[2]


def step_label(step: str) -> str:
    """Localised name of an installer stage (falls back to the raw name)."""
    from ..core import i18n

    key = f"wizard.stage.{step}"
    return i18n.t(key) if i18n.has(key) else step


def stage_names() -> tuple[str, ...]:
    """The installer stages, in order (mirrors the shell script's loop)."""
    return ("preflight", "layout", "llama", "python", "comfyui", "models", "verify")


#: Matches ``logs\kurulum-adim.txt``-style writes: not used by the shell script,
#: kept so a future ``--progress-file`` write can be validated in one place.
_PROGRESS_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s+(.*)$")


__all__ = [
    "INSTALL_PROFILES", "PROFILE_CHOICES", "repo_root", "find_install_script",
    "find_eula", "build_install_args", "build_smoke_args", "parse_progress",
    "step_label", "stage_names",
]
