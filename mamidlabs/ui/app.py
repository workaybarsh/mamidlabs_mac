"""Application entry point: the Qt6 desktop window.

The window is deliberately thin: all behaviour lives in :mod:`mamidlabs.core`,
so the GUI can be swapped (or run headless for tests) without touching the
engine.
"""

from __future__ import annotations

import sys

from ..core.paths import Paths
from ..core.settings import Settings


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    root = None
    if "--root" in argv:
        index = argv.index("--root")
        if index + 1 < len(argv):
            root = argv[index + 1]

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:  # pragma: no cover - only on a machine without PySide6
        print("PySide6 bulunamadı. Kurulum: scripts/install-mamidlabs.sh ya da\n"
              "  python3 -m pip install PySide6", file=sys.stderr)
        return 2

    from .main_window import MainWindow

    paths = Paths(root)
    settings = Settings(paths)

    app = QApplication.instance() or QApplication([argv[0] if argv else "mamidlabs"])
    app.setApplicationName("MamidLabs")
    app.setApplicationVersion("1.0.0")

    window = MainWindow(paths, settings)
    window.show()
    return app.exec()
