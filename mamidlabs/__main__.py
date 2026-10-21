"""``python -m mamidlabs`` — GUI by default, plus the headless subcommands the
shell scripts call (``manage``, ``profiles``, ``doctor``, ``version``).
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .core import i18n
from .core.paths import LLAMA_BUILD, Paths
from .core.profiles import PROFILE_IDS, catalog_for_display, get_profile, missing_files
from .core.settings import Settings


def _cmd_manage(args: argparse.Namespace) -> int:
    from .core.manage import ModelManager

    paths = Paths(args.root)
    settings = Settings(paths)
    manager = ModelManager(paths, settings)
    try:
        if args.action == "start":
            print(manager.start(args.profile or settings.local_profile))
        elif args.action == "stop":
            print(manager.stop())
        elif args.action == "closecomfy":
            print(manager.close_comfy())
        elif args.action == "status":
            print(manager.active_alias() or i18n.t("cli.not_loaded"))
    except Exception as exc:  # noqa: BLE001 - CLI surface
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def _cmd_profiles(args: argparse.Namespace) -> int:
    paths = Paths(args.root)
    if args.json:
        payload = []
        for profile in catalog_for_display():
            missing = missing_files(profile.id, paths)
            payload.append({
                "id": profile.id,
                "label": profile.label,
                "hardware": profile.hardware,
                "alias": profile.alias,
                "total_bytes": profile.total_bytes,
                "missing": [item.target for item in missing],
                "present": not missing,
            })
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    for profile in catalog_for_display():
        missing = missing_files(profile.id, paths)
        state = i18n.t("cli.ready") if not missing else i18n.t("cli.files_missing", count=len(missing))
        size = profile.total_bytes / (1024 ** 3)
        print(f"{profile.label:24} [{profile.id}] {state}  (~{size:.1f} GB)")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    """Report what is present and what is missing (no changes)."""
    paths = Paths(args.root)
    settings = Settings(paths)
    present, missing = i18n.t("cli.state.present"), i18n.t("cli.state.missing")
    print(i18n.t("cli.doctor.title", version=__version__))
    print(i18n.t("cli.doctor.root", root=paths.root))
    print(i18n.t("cli.doctor.llama", build=LLAMA_BUILD, path=paths.llama_server,
                 state=present if paths.llama_server.exists() else missing))
    print(i18n.t("cli.doctor.comfy",
                 state=present if paths.comfyui_main.exists() else missing))
    print(i18n.t("cli.doctor.settings", path=paths.settings_file,
                 state=present if paths.settings_file.exists()
                 else i18n.t("cli.state.will_create")))
    print(i18n.t("cli.doctor.secrets", backend=settings.secret_backend))
    from .core.manage import available_memory_mib, macos_total_mib

    total = macos_total_mib()
    available = available_memory_mib()
    if total:
        shown = available if available is not None else "?"
        print(f"Unified memory: {total} MiB total, {shown} MiB available")
    elif available is not None:
        print(f"Free memory   : {available} MiB")
    for env in ("app", "imagegen", "asr", "ocr"):
        python = paths.venv_python(env)
        print(i18n.t("cli.doctor.venv", env=env,
                     state=present if python.exists() else missing))
    for profile in catalog_for_display():
        miss = missing_files(profile.id, paths)
        state = i18n.t("cli.ready") if not miss else i18n.t("cli.files_missing", count=len(miss))
        print(i18n.t("cli.doctor.profile", profile=profile.id, state=state))
    return 0


def _cmd_version(_args: argparse.Namespace) -> int:
    print(f"MamidLabs {__version__}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mamidlabs", description=i18n.t("cli.desc"))
    parser.add_argument("--root", help=i18n.t("cli.help.root"))
    parser.add_argument("--lang", choices=list(i18n.SUPPORTED),
                        help="interface language (en|tr)")
    parser.add_argument("--version", action="version", version=f"MamidLabs {__version__}")
    sub = parser.add_subparsers(dest="command")

    manage = sub.add_parser("manage", help=i18n.t("cli.help.manage"))
    manage.add_argument("action", choices=["start", "stop", "closecomfy", "status"])
    manage.add_argument("--profile", choices=list(PROFILE_IDS))
    manage.set_defaults(func=_cmd_manage)

    profiles = sub.add_parser("profiles", help=i18n.t("cli.help.profiles"))
    profiles.add_argument("--json", action="store_true")
    profiles.set_defaults(func=_cmd_profiles)

    doctor = sub.add_parser("doctor", help=i18n.t("cli.help.doctor"))
    doctor.set_defaults(func=_cmd_doctor)

    version = sub.add_parser("version", help="print the version")
    version.set_defaults(func=_cmd_version)

    return parser


def _resolve_language(args: argparse.Namespace) -> str:
    """``--lang`` > settings file > environment > default."""
    if getattr(args, "lang", None):
        return i18n.set_language(args.lang)
    paths = Paths(args.root)
    try:
        code = Settings(paths).language
    except Exception:  # noqa: BLE001 - never let settings break the CLI
        code = i18n.language_from_env()
    return i18n.set_language(code)


def main(argv: list[str] | None = None) -> int:
    # Non-ASCII output must survive a redirected (non-UTF-8) console.
    i18n.configure_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    _resolve_language(args)
    if getattr(args, "func", None):
        return int(args.func(args))
    from .ui.app import main as gui_main

    forwarded = ["mamidlabs"]
    if args.root:
        forwarded += ["--root", args.root]
    if getattr(args, "lang", None):
        forwarded += ["--lang", args.lang]
    return int(gui_main(forwarded))


if __name__ == "__main__":
    raise SystemExit(main())
