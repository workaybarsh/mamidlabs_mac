# Changelog

This file lists user-visible changes. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[Semantic Versioning](https://semver.org/).

The single source of the version is `__version__` in `mamidlabs/__init__.py` and the
`version` field in `pyproject.toml` (the two must be equal).

## [1.0.0] — 2026-10-16

### Added
- **SHA256 verification and resumable downloads for profile downloads.** `mamidlabs/workers/
  hf-hub.py` compares the SHA256 digest of the downloaded file with Hugging Face's LFS digest
  (also offline when the catalog has the optional `sha256` field); if the digest does not
  match the file is **deleted** and a clear error is raised, so no silently corrupt model is
  left behind. Verification runs **before** MTP injection (the injection changes the file). An
  interrupted download is resumed by `hf_hub_download` and the worker reports this in the
  status line. Tests: `tests/test_model_download_integrity.py`.
- **Auto effort: MAX/FLASH behaviour based on question difficulty (without reloading the
  model).** Since MAX and FLASH are the same model, instead of switching profile the
  `reasoning_effort` is given per request for that turn: a short question/greeting `low`,
  medium `medium`, multi-step maths/code/analysis `xhigh`. The choice is made once at the
  start of the turn and stays fixed for the whole turn (the KV prefix is not broken). It can
  be turned off with **"Auto effort (by question)"** in the Profiles menu
  (`settings/api.json → autoEffort`). It does not apply to LITE or to API providers.
  Tests: `tests/test_auto_effort.py`.
- **Prompt injection hardening.** Web page, document, OCR and bound-file content is given to
  the model as **data** with the `[UNTRUSTED CONTENT …]` label; the fixed system prompt says
  the instructions in the content must not be applied. If untrusted content was read in that
  turn, approval is asked for `run_command` and `write_bound_file` **even with the "Full
  access" chip on** (`approval_required`), so an instruction hidden in the content cannot make
  the app act on the user's behalf. Tests: `tests/test_prompt_injection.py`.
- **Local RAG: offline (BM25) search in the bound folder.** The new `search_folder` tool finds
  the relevant text chunks in the bound folder before reading files one by one:
  `mamidlabs/workers/rag-tools.py` scans plain-text files (`node_modules`/`venv`/`.git` are
  skipped), produces ~900-character chunks that preserve line boundaries, and ranks them with
  BM25 + an exact-phrase bonus; the result is returned as `path:line`. The index is kept under
  `tools/rag/` and is not rebuilt while the source files are unchanged; no extra Python
  package is needed. The result is labelled as **untrusted data**, like other external
  sources. Tests: `tests/test_rag_tools.py`.
- **GitHub Actions release workflow (`.dmg`).** When a `v*` tag is pushed, the `.dmg` package
  is built and uploaded to the GitHub Release under a **fixed name** (`MamidLabs.dmg`), so
  `releases/latest/download/MamidLabs.dmg` always downloads the latest version directly. The
  single source of the version is `__version__` (its match with the tag is verified) and the
  release notes are read from `CHANGELOG.md`. Branch/PR runs only produce an artifact.
- **Setup wizard (Qt6).** **MamidLabs Setup.app** (or `scripts/mamidlabs-setup.sh`) opens a
  wizard that measures the hardware and suggests a suitable profile: language (English/TR) →
  welcome → licence → folder → hardware report → profile (LITE/PRO/no download/own model–API)
  → (your own models) → (API) → (components) → ready → install → summary → finish. 13 pages;
  `mamidlabs/wizard/`. The wizard writes the language and choices into `settings/api.json`,
  runs the installation through `install-mamidlabs.sh`, and reads progress from
  `logs/kurulum-adim.txt`.
- **Hardware measurement** (`mamidlabs/core/hwinfo.py`): recommendation based on **unified
  memory** and CPU family (Apple Silicon ≥ 32 GB → PRO, ≥ 16 GB → LITE; Intel Mac or little
  memory → API providers), the macOS version, the core count and the free disk.
- **`.dmg` package** (`packaging/macos/build-dmg.sh`): produces a disk image containing
  **MamidLabs Setup.app**; the `.app` runs `python3 -m mamidlabs.wizard` with embedded Python
  sources.
- **Runtime EN/TR localisation**: every interface, core, CLI and wizard string comes from the
  `mamidlabs/locales/{en,tr}.json` catalogs; the interface language changes instantly from the
  menu and from the wizard's first page. `--lang`, `--language`.
- `install-mamidlabs.sh --language en|tr` (writes to the settings file), plus progress
  (`logs/kurulum-adim.txt`) and summary (`logs/kurulum-ozeti.txt`) files for the wizard.
- New tests: `test_hwinfo.py`, `test_wizard.py` (pure), `test_wizard_gui.py` (headless Qt),
  `test_i18n.py`, `test_packaging_contract.py`, `test_model_download_integrity.py`,
  `test_auto_effort.py`, `test_prompt_injection.py`, `test_rag_tools.py` (203 tests in total).
- **MamidLabs macOS edition.** A complete macOS port of the Windows edition (`MamidLabsTR` /
  `MamidLabsENG`): a single-language **Python 3.12 + PySide6 (Qt6)** desktop application
  instead of WinForms/PowerShell.
- Qt6 main window: streaming chat, profile/provider/model selectors, Internet / Agent / Full
  access chips, model start-stop, tool approval dialog.
- API connections window; keys are stored preferably in the **macOS Keychain (keyring)**,
  otherwise in the `0600` settings file.
- Command-line interface: `python -m mamidlabs {doctor,profiles,manage}`.
- Bash install/management scripts: `install-mamidlabs.sh` (staged), `manage-mamidlabs.sh`,
  `uninstall-mamidlabs.sh`, `smoke-test.sh` (all compatible with macOS bash 3.2).
- **`MamidLabs.app`** application bundle (`Info.plist` + launcher) and a `.icns` icon
  generated from PNG; starts from Launchpad/Finder/Dock.
- Core modules: `paths` (macOS install root), `settings`, `profiles`, `providers` (OpenAI ↔
  Claude converters + streaming), `manage` (`ModelManager`, unified-memory gate,
  ComfyUI/orphan cleanup), `inference` (chat loop, tool loop, approval, context compaction),
  `tools` (tool registry + gates + web failure honesty), `chart`, `runner`.
- Python workers ported to macOS (web, document, OCR, media, whisper/transcriber,
  `mtp_inject`, `hf-hub`, `api-media`); the install root is now read from `MAMIDLABS_ROOT`
  (not derived from `__file__`).
- Unit tests (`pytest`); including memory-gate and platform-sensitive path tests.

### Fixed
- **Context overflow in long chats is now handled gracefully (Windows parity).** Compaction
  has two passes: first only the head of the oldest tool outputs is kept, and if that is not
  enough the oldest tool outputs and old assistant text are replaced with a short marker
  (messages are not deleted, the `tool_calls`/`tool` pairing is not broken). If the prompt
  still does not fit, tools are not offered at all and the model is asked for a **visible
  answer from the findings present** (`llama-server --no-context-shift` is used, so an
  overflowing prompt was a hard error). The output budget (`max_tokens`) is reduced to the
  remaining room and the "Approaching the context limit" note is only shown when something
  was actually shortened (no misleading note for nothing). Tests: `tests/test_inference.py`.

### Changed
- **The licence is now PolyForm Strict 1.0.0 (source-available; noncommercial use only).**
  `LICENSE` and `EULA.txt` carry the official PolyForm Strict 1.0.0 text: no right to
  distribute or modify/make new works based on the software; commercial use requires prior
  written permission. The README licence section and the licence test were updated
  accordingly; the `.dmg` build script already embeds `EULA.txt`/`LICENSE`. The version number
  did not change (1.0.0).

### Changed (compared with the Windows edition)
- macOS **Keychain** / `0600` file instead of Windows **DPAPI**.
- The system Python instead of the Windows **PowerShell 7 embedded runtime** (no `runtime/`
  in the install root).
- **Qt6** instead of Windows **WinForms**; **matplotlib** instead of `System.Drawing` graphics.
- **Metal instead of NVIDIA/CUDA:** llama.cpp `macos-arm64`/`macos-x64` build, torch/ComfyUI
  **MPS** (torch from PyPI; no CUDA index and no `nvidia-*` packages).
- **VRAM gate → unified-memory gate:** `vm_stat` (reclaimable pages) + `hw.pagesize` instead
  of `nvidia-smi`; overridable with `MAMIDLABS_FREE_MEM_MIB`.
- Audio transcription **on the CPU** on macOS (CTranslate2 has no Metal backend).
- 7-Zip path from Homebrew (`/opt/homebrew/bin`, `/usr/local/bin`) + PATH; PDF fonts from
  macOS system fonts + matplotlib DejaVu; HTTP User-Agent `Macintosh`.
- An **`.app` bundle** instead of `.desktop`; `run_command` runs with `/bin/zsh -lc`.

### Preserved
- Profile aliases (`qwen3.8-27b-max` / `-flash`, `qwen3.5-9b-lite`), model ids, tool names,
  server argument bundles, MTP, memory-gate headroom and the ComfyUI lifecycle — exactly the
  same as the Windows edition.
