"""``python -m mamidlabs.wizard`` — the setup wizard entry point.

Checks the environment *before* importing PySide6 so a headless machine or a
Python without Qt gets a clear one-line message instead of a traceback:

* no graphical session (Linux, no ``DISPLAY``/``WAYLAND_DISPLAY``) → exit 1
  with the ``wizard.error.no_display`` message;
* no PySide6 → exit 2 with ``wizard.error.no_pyside``.

The terminal installer (``scripts/install-mamidlabs.sh``) is always available as
the fallback.
"""

from __future__ import annotations

import sys

from ..core import i18n


def _has_display() -> bool:
    """True on platforms/desktops where a Qt window can open."""
    if sys.platform == "darwin":
        return True
    if sys.platform.startswith("win"):
        return True
    import os

    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def main(argv: list[str] | None = None) -> int:
    i18n.configure_console()
    i18n.set_language(i18n.language_from_env() if not _arg_lang(argv) else _arg_lang(argv))

    if not _has_display():
        print(i18n.t("wizard.error.no_display"), file=sys.stderr)
        return 1

    try:
        from .setup import main as gui_main  # noqa: PLC0415 - lazy on purpose
    except ImportError:
        print(i18n.t("wizard.error.no_pyside"), file=sys.stderr)
        return 2

    return int(gui_main(argv))


def _arg_lang(argv: list[str] | None) -> str | None:
    args = list(sys.argv if argv is None else argv)
    if "--lang" in args:
        index = args.index("--lang")
        if index + 1 < len(args):
            return args[index + 1]
    return None


if __name__ == "__main__":
    raise SystemExit(main())
