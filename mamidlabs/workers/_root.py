"""Resolve the install root for standalone workers.

The workers run as separate processes (often in their own virtualenvs) and may
not have the ``mamidlabs`` package importable, so they cannot use
``mamidlabs.core.paths``. They must not derive the root from their own location
either: the package lives in site-packages, not under the install root.
``MAMIDLABS_ROOT`` (set by the app for every child process) is the authoritative
source; the macOS default (``~/Library/Application Support/mamidlabs``, with an
XDG fallback on non-macOS hosts) is the fallback.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def install_root() -> Path:
    env = os.environ.get("MAMIDLABS_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    if sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support" / "mamidlabs").resolve()
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return (base / "mamidlabs").resolve()
