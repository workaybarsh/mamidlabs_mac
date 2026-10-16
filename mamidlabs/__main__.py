"""``python -m mamidlabs`` — GUI by default, plus the headless subcommands the
shell scripts call (``manage``, ``profiles``, ``doctor``, ``version``).
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
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
            print(manager.active_alias() or "Model yüklü değil.")
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
        state = "hazır" if not missing else f"{len(missing)} dosya eksik"
        size = profile.total_bytes / (1024 ** 3)
        print(f"{profile.label:24} [{profile.id}] {state}  (~{size:.1f} GB)")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    """Report what is present and what is missing (no changes)."""
    paths = Paths(args.root)
    settings = Settings(paths)
    print(f"MamidLabs {__version__}")
    print(f"Kurulum kökü : {paths.root}")
    print(f"llama.cpp    : {LLAMA_BUILD} -> {paths.llama_server} "
          f"({'var' if paths.llama_server.exists() else 'YOK'})")
    print(f"ComfyUI      : {'var' if paths.comfyui_main.exists() else 'YOK'}")
    print(f"Ayarlar      : {paths.settings_file} "
          f"({'var' if paths.settings_file.exists() else 'yeni oluşturulacak'})")
    print(f"Gizli anahtar deposu: {settings.secret_backend}")
    from .core.manage import available_memory_mib, macos_total_mib

    total = macos_total_mib()
    available = available_memory_mib()
    if total:
        shown = available if available is not None else "?"
        print(f"Birleşik bellek: toplam {total} MiB, kullanılabilir {shown} MiB")
    elif available is not None:
        print(f"Boş VRAM     : {available} MiB")
    for env in ("app", "imagegen", "asr", "ocr"):
        python = paths.venv_python(env)
        print(f"venv/{env:9}: {'var' if python.exists() else 'YOK'}")
    for profile in catalog_for_display():
        missing = missing_files(profile.id, paths)
        print(f"profil {profile.id:5}: {'hazır' if not missing else str(len(missing)) + ' dosya eksik'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mamidlabs", description="MamidLabs (macOS)")
    parser.add_argument("--root", help="kurulum kökü (varsayılan: ~/Library/Application Support/mamidlabs)")
    parser.add_argument("--version", action="version", version=f"MamidLabs {__version__}")
    sub = parser.add_subparsers(dest="command")

    manage = sub.add_parser("manage", help="yerel modeli başlat/durdur")
    manage.add_argument("action", choices=["start", "stop", "closecomfy", "status"])
    manage.add_argument("--profile", choices=list(PROFILE_IDS))
    manage.set_defaults(func=_cmd_manage)

    profiles = sub.add_parser("profiles", help="profil durumunu göster")
    profiles.add_argument("--json", action="store_true")
    profiles.set_defaults(func=_cmd_profiles)

    doctor = sub.add_parser("doctor", help="kurulumu denetle (değişiklik yapmaz)")
    doctor.set_defaults(func=_cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "func", None):
        return int(args.func(args))
    from .ui.app import main as gui_main

    forwarded = ["mamidlabs"]
    if args.root:
        forwarded += ["--root", args.root]
    return int(gui_main(forwarded))


if __name__ == "__main__":
    raise SystemExit(main())
