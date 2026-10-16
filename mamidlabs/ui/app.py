"""Application entry point: the Qt6 desktop window.

The window is deliberately thin: all behaviour lives in :mod:`mamidlabs.core`,
so the GUI can be swapped (or run headless for tests) without touching the
engine.
"""

from __future__ import annotations

import sys

from ..core import i18n
from ..core.paths import Paths
from ..core.settings import Settings


def _arg_value(argv: list[str], name: str) -> str | None:
    if name in argv:
        index = argv.index(name)
        if index + 1 < len(argv):
            return argv[index + 1]
    return None


def main(argv: list[str] | None = None) -> int:
    # The "PySide6 not found" notice is localised; make sure it can be printed.
    i18n.configure_console()
    argv = list(sys.argv if argv is None else argv)
    root = _arg_value(argv, "--root")
    lang = _arg_value(argv, "--lang")

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:  # pragma: no cover - only on a machine without PySide6
        print(i18n.t("app.no_pyside"), file=sys.stderr)
        return 2

    from .main_window import MainWindow

    paths = Paths(root)
    settings = Settings(paths)

    # Language precedence: --lang > settings file > environment > default.
    i18n.set_language(lang or settings.language or i18n.language_from_env())

    app = QApplication.instance() or QApplication([argv[0] if argv else "mamidlabs"])
    app.setApplicationName(i18n.t("app.name"))
    app.setApplicationVersion("1.0.0")

    window = MainWindow(paths, settings)
    window.show()
    return app.exec()
