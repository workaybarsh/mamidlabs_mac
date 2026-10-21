# MamidLabs · Infrastructure guide for developers and AI agents (macOS)

This file is the single source of truth for developers and AI agents working on the MamidLabs
macOS edition. It explains how the codebase is started, how the parts talk to each other,
where everything lives, and the known pitfalls.

> **Mandatory rule:** when you add a feature, change a behaviour or find a new pitfall,
> update this file **in the same commit**: fix the relevant section and add a line to the
> [changelog](#15-changelog) at the bottom. User-visible changes are also written to
> `CHANGELOG.md`. If code and this file disagree, **the code is right**; whoever notices the
> conflict fixes this file.

The language of communication with the user is **English**. Code comments and script texts
are English.

---

## 1. The product in one paragraph

MamidLabs is a multimodal AI workspace that runs fully locally on macOS. In a single Qt6
window it offers chat, web search, document reading/creation, OCR, image understanding, image
generation, photo editing, video generation, chart drawing and audio transcription. The
language model runs on `llama.cpp` (`llama-server`), the image/video models on `ComfyUI`,
using the Mac's **Metal** accelerator (llama.cpp Metal; torch/ComfyUI MPS). OpenAI, Claude,
Gemini, DeepSeek and custom OpenAI-compatible endpoints are optional API providers.
Repository: `github.com/workaybarsh/mamidlabs_mac`. The default install root is
`~/Library/Application Support/mamidlabs`.

This edition is the **macOS port** of the Windows edition (`MamidLabsTR` / `MamidLabsENG`):
**Python 3.12 + PySide6 (Qt6)** instead of WinForms/PowerShell. Constants, behaviours and the
tool set are kept identical to the Windows edition.

## 2. Repository map

| Path | Contents |
|---|---|
| `mamidlabs/__main__.py` | Entry point: `doctor`, `profiles`, `manage` subcommands; otherwise the GUI |
| `mamidlabs/ui/app.py` | Qt6 `QApplication` + main window setup |
| `mamidlabs/ui/main_window.py` | Main window, chat, profile/provider selectors, chips, `TurnWorker`/`ManageWorker` |
| `mamidlabs/ui/settings_dialog.py` | API connections window, key validation |
| `mamidlabs/ui/theme.py` | Qt stylesheet |
| `mamidlabs/core/i18n.py` | Runtime localisation (EN source; TR falls back) |
| `mamidlabs/locales/{en,tr}.json` | Interface texts (EN source, TR translation) |
| `mamidlabs/core/hwinfo.py` | Hardware measurement + profile recommendation (unified memory; wizard step 5) |
| `mamidlabs/wizard/` | Setup wizard: `__init__.py` (pure helpers), `setup.py` (Qt6 `QWizard`, 13 pages), `__main__.py` (entry + desktop check) |
| `mamidlabs/core/paths.py` | macOS install root and all paths (`is_macos`, `default_root`) |
| `mamidlabs/core/settings.py` | `api.json` store (atomic write, `0600`), `SecretStore`, `secret_backend` |
| `mamidlabs/core/profiles.py` | Profile catalog, aliases, target paths, missing files |
| `mamidlabs/core/providers.py` | Provider table, OpenAI ↔ Claude converters, streaming (SSE) |
| `mamidlabs/core/manage.py` | `ModelManager`: start/stop, memory gate, `server_args`, ComfyUI/orphan cleanup, `FileLock` |
| `mamidlabs/core/inference.py` | `InferenceEngine`: chat loop, system prompt, tool loop, approval, compaction, web honesty |
| `mamidlabs/core/tools.py` | `ToolRegistry` (gates + handlers), `WebTracker`, `MediaBridge` |
| `mamidlabs/core/chart.py` | matplotlib chart generation + safe expression evaluator |
| `mamidlabs/core/runner.py` | `WorkerRunner`: runs workers over JSON stdin/stdout |
| `mamidlabs/workers/` | Platform-independent Python workers (see below) |
| `scripts/install-mamidlabs.sh` | Staged installation (Homebrew/Metal/MPS) |
| `scripts/manage-mamidlabs.sh` | Model/ComfyUI management, doctor, profiles |
| `scripts/uninstall-mamidlabs.sh` | Complete uninstall (touches nothing outside the root) |
| `scripts/smoke-test.sh` | End-to-end verification with real models |
| `scripts/mamidlabs-setup.sh` | Launches the setup wizard (`python3 -m mamidlabs.wizard`) |
| `packaging/macos/build-dmg.sh` | Produces the `.dmg` (embeds the wizard `.app`); `packaging/macos/README.md` |
| `packaging/Info.plist`, `packaging/MacOS-MamidLabs` | application `.app` templates (`@VERSION@`, `@ROOT@` placeholders) |
| `packaging/macos/Info.plist`, `packaging/macos/MacOS-MamidLabsSetup` | wizard `.app` templates |
| `packaging/mamidlabs.png`, `packaging/mamidlabs.svg` | Icon (the `.icns` is generated at build time) |
| `requirements/{app,imagegen,asr,ocr}.txt` | Python packages (pinned versions) |
| `tests/` | pytest (203 tests; PySide6 not required) |
| `docs/` | `install.md`, `technical-notes.md` |
| `.github/workflows/tests.yml` | CI (macos-latest, Python 3.12) |
| `.github/workflows/installer.yml` | Release: on a `v*` tag builds the `.dmg` and uploads it to the GitHub Release under a fixed name (`MamidLabs.dmg`) |
| `AGENTS.md` | This guide. Not copied into the install root. |

### Workers (`mamidlabs/workers/`)

One-shot JSON stdin/stdout contract. Each worker runs in its own virtual environment.

| Worker | Environment | Job |
|---|---|---|
| `mamidlabs-agent-tools.py` | app | Web search (`ddgs`), page reading, reference image |
| `office-tools.py` | app | PDF/Word/Excel/PPTX/ZIP/RAR reading, PDF/DOCX/PPTX/XLSX creation |
| `ocr-tools.py` | ocr | PaddleOCR (CPU) |
| `media-tools.py` | imagegen | Video frame extraction (PyAV) |
| `api-media.py` | app | Image/video generation through an API |
| `hf-hub.py` | app | Hugging Face download (size + SHA256 verified, resumes where it stopped) |
| `mtp_inject.py` | app | Adds the MTP/nextn header to the LITE GGUF |
| `whisper-tools.py` | asr | Audio transcription (calls the `transcriber/` package; CPU on macOS) |
| `transcriber/` | asr | faster-whisper + AST + pyannote pipeline |
| `rag-tools.py` | app | Local (offline) BM25 search in the bound folder (`search_folder`) |
| `_root.py` | — | Workers read the install root (`MAMIDLABS_ROOT` → Library) |

## 3. Install root layout

```
~/Library/Application Support/mamidlabs/
  llama.cpp/b10998/llama-server     pinned llama.cpp build (Metal)
  models/                           GGUF language models (+ mmproj)
  ComfyUI/                          pinned commit; custom_nodes: ComfyUI-GGUF, comfyui-krea2edit
  venv/{app,imagegen,asr,ocr}/      Python environments (bin/python)
  tools/{hf-home,downloads,pip-cache,backup,rag}/
  settings/api.json                 all user settings (secrets 0600)
  chats/  outputs/{images,videos,documents,charts,refs,thumbs,input}/
  logs/                             llama-server-*.std{out,err}.log, comfyui.*.log, audit.jsonl
  mamidlabs-launch                  launcher (the script the .app bundle calls)
```

The installer also creates the **`~/Applications/MamidLabs.app`** bundle
(`Contents/Info.plist`, `Contents/MacOS/MamidLabs`, `Contents/Resources/mamidlabs.icns`).

As on Windows there is **no embedded runtime** (there is no `runtime/`): the application runs
with the system Python.

## 4. Startup chain

1. `MamidLabs.app` → `Contents/MacOS/MamidLabs` (generated with `@ROOT@` at install time).
2. This script runs the `~/Library/Application Support/mamidlabs/mamidlabs-launch` script.
3. Launcher: sets `MAMIDLABS_ROOT` and runs `venv/app/bin/python -m mamidlabs`.
4. `mamidlabs/__main__.py` parses the arguments; without a subcommand it calls `ui/app.py:main`.
5. `ui/app.py`: `Paths`, `Settings`, `QApplication`, `MainWindow`.
6. `MainWindow` prepares the paths and sets up `ModelManager`/`ToolRegistry`/`InferenceEngine`.
7. When the user picks a profile and presses **Start model**, `ManageWorker` → `ModelManager.start`.
8. When the application closes, the server and the idle ComfyUI are shut down (memory is freed).

## 5. Processes and ports

| Process | Port | Owner |
|---|---|---|
| `llama-server` | 8080 | `core/manage.py` (`ModelManager`) |
| ComfyUI | 8188 | media bridge / `manage-mamidlabs.sh comfy` |
| Transcription worker | random (127.0.0.1) | `core/inference.py` |

**Profiles** (`core/profiles.py`; aliases are the same as on Windows):

| Profile | Alias | Important flags |
|---|---|---|
| MAX | `qwen3.8-27b-max` | ctx 32768, predict 8192, gpu-layers 99, q4_0 KV, cache-reuse 256, batch 512/256, threads 6/12, `--mmproj --no-mmproj-offload --image-min-tokens 1024`, `--reasoning-effort xhigh`, `--spec-type draft-mtp` when MTP is present |
| FLASH | `qwen3.8-27b-flash` | the same files; `--reasoning-effort low` |
| LITE | `qwen3.5-9b-lite` | ctx `liteContext` (32768), predict 8192, batch 256/128, threads 4/8, `--image-min-tokens 512`, `--reasoning-effort low`, `--spec-type draft-mtp` when MTP is present |

The server arguments are **exactly the same** as in the Windows edition; on macOS Metal is
already the default backend, so no separate flag is needed (`--gpu-layers 99` applies to Metal
too). MAX and FLASH use the same files → a single "Qwen3.8 MAX" entry in the interface
(`catalog_for_display`). Lookup by id uses the full catalog (`get_profile`).

**MTP.** `--spec-type draft-mtp` is only added when the GGUF actually carries MTP/`nextn`
layers (`manage.gguf_has_mtp`); given to a model without them, llama.cpp will not start.
LITE's 9B GGUF loses the header during conversion and it is added back with `mtp_inject.py`
during the download. Disable it with `settings.mtp=false`.

**Auto effort (MAX/FLASH).** MAX and FLASH are the same model; the only difference is the
server's `--reasoning-effort` value. Because changing profile reloads the model (~15 s), by
default the effort is given **per request** (Profiles → **"Auto effort (by question)"**)
through `chat_template_kwargs.reasoning_effort`: a short question/greeting → `low`, medium →
`medium`, multi-step maths/code/analysis/comparison → `xhigh`
(`inference.auto_reasoning_effort`). The choice is made **once at the start of the turn** and
stays fixed for the whole turn (so the system prefix does not change and the KV cache is not
broken). When off, the server's profile value is used (`api.json → autoEffort=false`). LITE's
template ignores this key; it is not sent to API providers.

**Download and verification.** `hf-hub.py` verifies the size with `bytes`, **resumes** the
missing file with `hf_hub_download`, and verifies **SHA256** once the download finishes: the
pinned `sha256` from the catalog when present, otherwise the `lfs.sha256` digest in the
Hugging Face LFS metadata (cached per repo/revision). If the digest does not match, the
corrupt file is **deleted**; verification happens **before** MTP injection because the
injection changes the file. `HF_HOME` is under the root.

**Memory gate** (`manage.ModelManager`): needed = model file + headroom. MAX/FLASH headroom
**750 MiB**, tolerance **0** (available < needed → error). LITE headroom **300 MiB**,
tolerance **1024 MiB** (warning band `[needed-1024, needed)`). The vision projector is on the
CPU in all three profiles (`--no-mmproj-offload`) and does not count against the budget.

macOS has **no separate VRAM**: `available_memory_mib()` returns the reclaimable amount from
unified memory (`vm_stat`: free + inactive + speculative + purgeable; multiplied by
`hw.pagesize`). The `MAMIDLABS_FREE_MEM_MIB` environment variable overrides the measurement
(for tests and manual tuning). On non-macOS hosts (`sys.platform != "darwin"`) `nvidia-smi`
and `/proc/meminfo` are tried in that order. `macos_total_mib()` returns the total unified
memory (information only). Before the model loads, leftover GPU workers
(`stop_orphan_workers`) are closed.

**ComfyUI lifecycle:** by default it runs **only during media generation**
(`comfyKeepAlive=false`); it is closed before the language model loads. On LITE it can be kept
open with `comfyKeepAlive=true`. Leaked/duplicate instances are counted by process **roots**
(ComfyUI is a process pair); the single instance listening on `:8188` is kept.

## 6. Chat request flow

1. The user sends → `MainWindow._send` → `TurnWorker` (`QThread`).
2. `InferenceEngine.build_job_messages`: fixed `SYSTEM_PROMPT` + history. Image data from old
   turns is dropped and replaced with a note. Turn-specific hints are added **to the start of
   the last user message**, not to the system prompt (so the KV cache prefix is not broken).
3. `run_turn` produces events (to the interface through the `event` signal): `thinking`,
   `answer`, `status`, `tool`, `denied`, `error`, `done`, `cancelled`.
4. **Tools** (`core/tools.py`): `search_web`, `fetch_page`, `read_document`,
   `read_images_ocr`, `create_document`, `generate_image`, `generate_video`, `generate_chart`,
   `find_reference_image`, `ask_model`, `list_bound_files`, `read_bound_file`, `search_folder`,
   `write_bound_file`, `run_command`. Tools are offered according to intent and chips;
   production tools are re-checked at call time.
5. **Approval:** write/execute tools are asked through the `approve` callback
   (`TurnWorker._approve` → `approval_needed` signal → `QMessageBox`). A 10 min timeout →
   denied. When the "Full access" chip is on they are normally not asked; **however, if
   untrusted content** (`search_web`, `fetch_page`, `read_document`, `read_images_ocr`,
   `read_bound_file`, `search_folder`) **was read in that turn, `run_command` and
   `write_bound_file` still ask** (`approval_required`); the approval dialog also states the
   reason (`chat.approval_untrusted`). The result of untrusted content is given to the model
   with the `chat.untrusted_prefix` label, and the system prompt (`prompt.untrusted`) says this
   content is **data, not instructions** (defence against prompt injection).
6. **The `done` event** carries the `assistant.tool_calls` and `tool` messages added in that
   turn in its `data` field; the interface appends them to the persistent history. Otherwise
   in the next turn the client prefix differs from the server's and the context is processed
   from scratch.
7. **Context protection** (Windows parity): if at the start of a turn the estimated prompt +
   `max_tokens` + headroom would exceed the context, `compact_turn_messages` shortens with
   **two passes** — first only the head of the oldest tool outputs, and if that is not enough
   the oldest tool outputs and old assistant text are replaced with a short marker (messages
   are not deleted; the `tool_calls`/`tool` pairing is preserved). **If it still does not
   fit**, tools are **not offered** and the model is asked for a visible answer from the
   findings present (`chat.context_full`); `max_tokens` is reduced to the remaining room. The
   "compacted" status note is only shown when something was actually shortened.

### Web failure honesty

The decision depends on **web was attempted AND there was no successful call**
(`WebTracker.unavailable = fail_count > 0 and not success`). Partial success (e.g. 4 of 7
calls succeed) does **not** count as failure. After ≥2 failures the web tools lock
(`should_lock_tools = fail_count >= 2 and not success`). `add_failure_note` returns early when
there is a success. On a turn that asks for current information without the web, the model's
text is not used; an honest message is shown, and fabricated citations
(`strip_fabricated_citations`) are stripped.

## 7. Image, photo editing and video

- When the model calls `generate_image`, `MediaBridge` (the bridge supplied by the interface)
  drives ComfyUI. The language model only writes the prompt.
- **Modes** (`generate_image.mode`): `yeni` (from text), `yeniden_uret` / `stil_referansi`
  (from an attached image), `kimlik_duzenle` (Krea 2 Identity Edit LoRA; **MAX/FLASH only** —
  not offered on LITE because there is not enough memory).
- Video: Wan 2.2 TI2V 5B; modes `metin`, `gorsel`, `video`.
- External model files are used without copying: ComfyUI `--extra-model-paths-config`.
- On macOS ComfyUI runs with **MPS**; it is noticeably slower than CUDA and some custom nodes
  can only run on the CPU. The torch in the `imagegen` environment is the PyPI wheel (MPS
  built in); a separate CUDA index is **not used**.
- API media: when the image/video provider is an API, `api-media.py` is used.

## 8. API providers

- A single table: `core/providers.py`: `openai`, `claude`, `gemini`, `deepseek`, `custom`. A
  new provider = one row in the table (+ a converter if needed).
- **`custom`** ("Custom (OpenAI-compatible)"): Ollama, LM Studio, vLLM etc. The base URL is
  read from settings; **the key is optional** (no `Authorization` when empty).
- **Claude:** `thinking` is not sent; `tool_choice` is `auto` only when present in the body;
  the `max_tokens` floor is 16000; in the tool loop the signed `thinking` blocks are collected
  by `ClaudeStream` and sent back through the first `tool_use` id.
- **DeepSeek** does not accept images; `image_url` parts are flattened into a text note.
- Keys are stored preferably in the **macOS login keychain** (`keyring` / Keychain), otherwise
  in `settings/api.json` with `0600` permissions. `Settings.secret_backend` reports which is
  used.

## 9. Profiles, catalog and download

- `core/profiles.py`: the file list per profile (`target` relative to the root, `repo`,
  `revision`, `filename`, `bytes`, optional `sha256`).
- Download sizes: LITE ~36 GB, MAX/FLASH ~52 GB. `hf-hub.py` verifies the size with `bytes`,
  resumes the missing file where it stopped (`hf_hub_download`), and verifies **SHA256** once
  the download finishes: the pinned `sha256` from the catalog when present, otherwise the
  `lfs.sha256` digest in the Hugging Face LFS metadata (cached per repo/revision). On a
  mismatch the corrupt file is **deleted** and an error is raised. `HF_HOME` is under the root.
- Profile status looks only at the **existence** of the file, it does not compare sizes.
- **Profile deletion:** only files **specific** to that profile are deleted (`unique_targets`);
  shared ones are kept. Since MAX and FLASH are the same set, they count as one alias.

## 10. Install, update and uninstall

- `install-mamidlabs.sh [--root] [--profile] [--language en|tr] [--stage a,b]
  [--skip-media] [--skip-audio] [--skip-ocr] [--skip-models] [--no-desktop]
  [--no-cuda] [--force]`. Stages: `preflight`, `layout`, `llama`, `python`, `comfyui`,
  `models`, `verify`. `--language` writes the choice into `settings/api.json`; the stage loop
  writes progress into `logs/kurulum-adim.txt` (lines 1/2/3: step number, total, name) and the
  summary into `logs/kurulum-ozeti.txt` at the end (the wizard reads these).
- **Wizard and DMG:** `packaging/macos/build-dmg.sh` produces a `.dmg` containing
  **MamidLabs Setup.app** (`hdiutil`, `-format UDZO`); the app bundle carries the embedded
  Python sources under `Contents/Resources/mamidlabs-src` and runs
  `python3 -m mamidlabs.wizard`. From source, `./scripts/mamidlabs-setup.sh` opens the same
  wizard.
- The script is compatible with **macOS bash 3.2** (no associative arrays, no `mapfile`, no
  `${var,,}`); the shebang is `#!/bin/bash`.
- `layout` installs the program files, the launcher and the `~/Applications/MamidLabs.app`
  bundle; the `.icns` icon is generated from PNG with `sips`/`iconutil` (installed without an
  icon if missing).
- The `llama` stage downloads `llama-<build>-bin-macos-arm64.zip` or `-macos-x64.zip`
  depending on the architecture and extracts `llama-server` + `*.dylib` (Metal).
- The `python` stage installs torch **from PyPI** (MPS built in): `torch torchvision
  torchaudio` for imagegen, `torch torchaudio` for asr, `paddlepaddle` (CPU) for ocr. No CUDA
  index is used.
- Pinned versions: llama.cpp `b10998`, ComfyUI `b0f4b7b`, ComfyUI-GGUF `6ea2651`,
  comfyui-krea2edit `86f886d`.
- **Uninstall:** `uninstall-mamidlabs.sh [--keep-user-data] [--dry-run] [--yes]`. It only
  touches the root and the `~/Applications/MamidLabs.app` bundle; it refuses to run on
  system/user folders.
- **Update:** close the app → `git pull` → `install-mamidlabs.sh --stage layout`.
- **Version and release:** the single source of the version is
  `mamidlabs/__init__.py:__version__` and `pyproject.toml:version` (must be equal). New
  release: bump both, add a section to `CHANGELOG.md`, push the `v<version>` tag. When the tag
  is pushed, `.github/workflows/installer.yml` builds the `.dmg` and uploads it to the GitHub
  Release under a **fixed name** (`MamidLabs.dmg`); `releases/latest/download/MamidLabs.dmg`
  therefore always downloads the latest version.

## 11. Settings and user data

`settings/api.json` (the application keeps it in memory; it writes on change and on exit;
**editing it by hand while the app is open is overwritten**):

- Model selection: `selected`, `selectedModel`, `selectedLocalModel`, `localProfile`.
- Providers: `providers.<id>.{key, model, models, contextLimit, baseUrl}`.
- Your own models: `localModels`, `imageLocalModel`, `videoLocalModel`, `imageProvider`,
  `videoProvider`, `externalMediaModels`.
- Interface: `uiPreferences.{internet, agent, accessMode}`, `firstRunApiSettings`.
- LITE: `liteModel`, `liteContext`.
- Media: `comfyKeepAlive` (default `false`).
- Audio: `audioEvents` (default `true`).
- Other: `mtp` (default `true`), `autoEffort` (default `true`), `boundFolder`.
- Secrets: the macOS Keychain or this file (`0600`).

Chats are stored under `chats/`. `logs/audit.jsonl`: a record of tool calls (not content;
path/command id).

## 12. Tests

```bash
python3 -m pip install pytest -r requirements/app.txt
python3 -m pytest -q          # 203 tests; PySide6 not required (only the wizard window tests)
./scripts/smoke-test.sh --profile flash
```

- `conftest.py` points `MAMIDLABS_ROOT` at a temporary root, so the tests run independently of
  `__file__`. The autouse fixture in the same file resets the process-global language state
  (`i18n`) to the default (English) before and after every test.
- Tests for new behaviour: `test_model_download_integrity.py` (`sha256_file`,
  `lookup_sha256`/`verify_sha256`, `incomplete_bytes`, `_mtp_config`, fetch protection),
  `test_auto_effort.py` (`auto_reasoning_effort` score + `chat_template_kwargs` in the request
  body), `test_prompt_injection.py` (untrusted content label, system prompt, approval even
  under full access), `test_rag_tools.py` (`rag-tools.py` BM25 + the `search_folder` gate).
- `tests/test_wizard.py` tests the pure helpers without Qt; `tests/test_wizard_gui.py` tries to
  open the wizard window headlessly and is skipped when Qt cannot be loaded (e.g. a missing
  system library).
- The tests do **not import** PySide6; the core logic is pure Python. The GUI only runs on a
  real desktop (in the interface steps of the smoke test).
- `test_paths.py` is platform-sensitive: on macOS `default_root()` returns the Library path
  and the XDG test is skipped.
- `manage.FileLock` uses `fcntl` on POSIX (`macOS`/Linux) and `msvcrt` on Windows.
- **Memory tests:** `MAMIDLABS_FREE_MEM_MIB` overrides the measurement;
  `_macos_available_mib` parses the `vm_stat` output (tested with a fake `subprocess.run`).
- **Smoke test steps:** `doctor`, `server_start`, `health`, `chat`, `chart`, `offline`, `mtp`,
  `ocr`, `image`, `video`, `server_stop`. The result is written to
  `logs/smoke-test-son.json`.
- **CI:** `tests.yml` on every push/PR (macos-latest, Python 3.12).

## 13. Hardware facts

On macOS speed depends on **Metal** and on the amount of **unified memory**. The NVIDIA
measurements (Windows/Linux) are a reference; on Apple Silicon the chat token rate is similar,
while image/video generation (MPS) is slower than CUDA.

| | 32 GB unified memory (MAX/FLASH) | 16 GB unified memory (LITE) |
|---|---|---|
| Chat | smooth on Metal (MTP on) | smooth on Metal (MTP on) |
| Image (`new`) | on the order of minutes (MPS) | on the order of minutes (MPS) |
| Photo editing | supported | **not supported** |
| Audio transcription | CPU (int8) | CPU (int8) |

The 27B model occupies ~15 GB of the GPU/GPU-like budget (the file is ~14.6 GB; plus the
q4_0 KV cache + compute buffers + the MTP draft context). That is why the MAX/FLASH headroom
is **750 MiB**: the model only loads if it fits **completely** and then uses **all available
memory**.

**Why `kimlik_duzenle` is missing on LITE:** Krea2EditGroundedEncode keeps the text/image
encoder (~5 GB) and the diffusion model (~7.5 GB) in the same graph, which exceeds the LITE
budget. That is why the mode is not offered at all on LITE.

**Audio transcription:** on macOS CTranslate2 has no Metal backend; the whole pipeline runs on
the CPU (int8). A language-model swap is therefore not needed and `choose_plan` always returns
`('cpu', False)` on macOS.

## 14. Critical pitfalls

1. **Never derive the install root from `__file__`.** The package lives inside
   `site-packages`; workers read the root from `MAMIDLABS_ROOT` →
   `~/Library/Application Support/mamidlabs` (`workers/_root.py`). When you add a new path to
   a worker, do not hardcode it.
2. **KV cache match.** The message array the interface stores must be byte-for-byte identical
   to what the server processes in that turn. If a tool call/result is not stored, or the
   system prompt changes per turn, the context is processed from scratch on every turn. Put
   turn-specific text in the last user message.
3. **Memory headroom depends on the profile** (MAX/FLASH 750 MiB tolerance 0; LITE 300 MiB
   tolerance 1024 MiB). On macOS the measurement comes from `vm_stat`; "Pages free" is **not
   used alone** (macOS deliberately keeps a large file cache) — the reclaimable pages (free +
   inactive + speculative + purgeable) are summed. Before the model loads an idle ComfyUI is
   **always** closed.
4. **ComfyUI is a process pair** (venv launcher + base python child). A leak is decided by
   process **roots**, not by process **count**; a single healthy instance is already 2
   processes.
5. **`/proc` does not exist on macOS.** `manage._exe_for` returns empty outside Linux (root
   matching uses the full command line from `ps -ww`); the port listener is found via `/proc`
   on Linux and via `lsof` on macOS.
6. **`fcntl` is POSIX-specific.** It exists on macOS; `manage.FileLock` still imports it lazily
   and falls back to `msvcrt` on Windows (the tests pass on Windows too).
7. **`done.data` can be empty.** Without tool calls the worker puts an empty list; the
   interface uses an `if data:` guard (do not merge an empty array unconditionally).
8. **Single-image rule.** Only one image goes into a chat at a time (multiple images only via
   OCR).
9. **Do not edit `settings/api.json` by hand while the app is open;** on exit the in-memory
   copy is written.
10. **`run_command` runs with `/bin/zsh -lc`** (the macOS default shell) and asks for user
    approval. Shell escaping differs from the `.cmd` pitfalls on Windows; keep the command on
    a single line.
11. **PySide6 is only needed on a real desktop.** The core tests do not import the GUI; CI
    passes without PySide6 installed.
12. **The version lives in two places:** `mamidlabs/__init__.py:__version__` and
    `pyproject.toml:version`. Bump both together.
13. **The `.app` templates contain placeholders;** `packaging/Info.plist` has `@VERSION@`,
    `packaging/MacOS-MamidLabs` has `@ROOT@`. The installer replaces them with `sed`. Do not
    copy them directly.
14. **macOS bash 3.2.** Do **not** use bash 4+ features in scripts (associative arrays,
    `mapfile`, `${var,,}`, `local -n`); `realpath -m` is missing too (use Python's
    `os.path.abspath` instead).
15. **Do not use a CUDA index.** macOS torch wheels come from PyPI with MPS built in; indexes
    such as `download.pytorch.org/whl/cu130` do not work on macOS.
    `nvidia-cublas-cu12`/`nvidia-cudnn-cu12` do not exist for macOS and are **not** in
    requirements/asr.txt.
16. **The wizard needs Qt and a desktop.** `python3 -m mamidlabs.wizard` exits with code **2**
    and `wizard.error.no_pyside` when PySide6 is missing (`wizard/setup.py` is therefore
    imported lazily); there is no `DISPLAY` check on macOS. The wizard's pure helpers
    (`wizard/__init__.py`) are tested without Qt. The recommendation looks at **unified
    memory** and Apple Silicon; a local profile is not recommended for an Intel Mac.
17. **macOS bash 3.2.** All `scripts/*.sh`, including the wizard/packaging scripts, use
    `#!/bin/bash` and contain no bash 4+ features; `packaging/macos/build-dmg.sh` only runs on
    macOS (`hdiutil`) and is only checked with `bash -n` in CI.
18. **The RAG index is untrusted content.** The `search_folder` result goes to the model with
    the `[UNTRUSTED CONTENT…]` label and triggers write/execute approval in that turn. The
    index is kept in `tools/rag/bound-<hash>.json`; the hash is taken from **the real path
    exactly as-is** (not lower-cased) (same as the Linux edition; macOS volumes are usually
    case-insensitive). `hf-hub.py` sets `HF_HOME` **before the import**; on a SHA256 mismatch
    the downloaded file is deleted (never leave a silently corrupt model).

## 15. Checklist when making changes

- [ ] Run the relevant tests; add a test for new behaviour (`python -m pytest -q`).
- [ ] Is the user-visible text in English, with the correct characters?
- [ ] Install/uninstall impact: does a new file or folder write outside the root? If so, add it
      to the uninstaller. By default everything must stay under the root (single exception:
      `~/Applications/MamidLabs.app`).
- [ ] Are `README.md`, `docs/install.md`, `docs/technical-notes.md`, `CHANGELOG.md` and **this
      file** up to date?
- [ ] Did the server arguments or profile constants change? (Keep the alignment with the
      Windows edition.)
- [ ] Are the script changes compatible with bash 3.2 (`bash -n` is not enough; make sure no
      bash 4+ feature is used)?
- [ ] If a release is being cut: are `__version__` + `pyproject.toml`, the CHANGELOG section and
      the `v<version>` tag consistent?

## 16. Changelog

Add one line for every feature/change (newest at the top).

| Date | Change | Files |
|---|---|---|
| 2026-10-18 | **Licence brought to parity with the Windows edition: PolyForm Strict 1.0.0 (source-available; noncommercial use only).** `LICENSE` (no BOM, LF, 3619 bytes) and `EULA.txt` (UTF-8 BOM, 4833 bytes) were copied **byte-for-byte** from the Windows `MamidLabsTR` repository; the README licence section and the licence test in `tests/test_packaging_contract.py` (LICENSE heading + EULA BOM) were updated; the `.dmg` script already embeds `EULA.txt`/`LICENSE`. The `pyproject.toml` classifier stays `License :: Other/Proprietary License` (PolyForm is not OSI-approved). Version unchanged (1.0.0). | LICENSE, EULA.txt, README.md, tests/test_packaging_contract.py, CHANGELOG.md, AGENTS.md |
| 2026-10-18 | **Context compaction: overflow in long chats is handled gracefully (Windows parity).** Compaction has two passes (first the head of the tool output, then, if that is not enough, the tool/assistant text is replaced with a short marker; messages are not deleted, the `tool_calls`/`tool` pairing is preserved). If the prompt still does not fit, tools are not offered, the model is asked for a visible answer from the findings present, and `max_tokens` is reduced to the remaining room; the "compacted" status note is only shown when something was actually shortened. | mamidlabs/core/inference.py, mamidlabs/locales/{en,tr}.json, tests/test_inference.py, AGENTS.md, CHANGELOG.md, docs/technical-notes.md |
| 2026-10-18 | **Local (offline) RAG in the bound folder: the `search_folder` tool.** The new `rag-tools.py` worker scans the bound folder and returns the most relevant text chunks in `[file:line]` form using BM25 (k1=1.2, b=0.75 + a 1.6× exact-phrase bonus); the index is cached in `tools/rag/bound-<hash>.json` with a file signature (path+mtime+size) and is rebuilt silently when corrupt. Folders such as `node_modules`/`.git`/`venv` and binary/oversized files are skipped; decoding is utf-8 → cp1254 → latin-1. The tool goes through the same gate as the bound-folder file tools (not offered on an audio turn; offered when `is_file_intent`) and counts as **untrusted**. | mamidlabs/workers/rag-tools.py, mamidlabs/core/tools.py, mamidlabs/core/paths.py, tests/test_rag_tools.py |
| 2026-10-18 | **Hardening against prompt injection.** The results of `search_web`/`fetch_page`/`read_document`/`read_images_ocr`/`read_bound_file`/`search_folder` are given to the model with the `chat.untrusted_prefix` label; the system prompt (`prompt.untrusted`) says this content is **data, not instructions**. If untrusted content was read in that turn, `run_command`/`write_bound_file` ask for approval even with the "Full access" chip on (`inference.approval_required`); the approval dialog also states the reason (`chat.approval_untrusted`). | mamidlabs/core/inference.py, mamidlabs/ui/main_window.py, mamidlabs/locales/*, tests/test_prompt_injection.py |
| 2026-10-18 | **Auto effort (per request for MAX/FLASH).** Since MAX and FLASH are the same model, when `Profiles → "Auto effort (by question)"` is on (`api.json:autoEffort`, default `true`), `inference.auto_reasoning_effort` picks `low`/`medium`/`xhigh` per turn and puts it in the request body as `chat_template_kwargs.reasoning_effort` (local provider only; the LITE template ignores it). The choice is fixed for the whole turn → the model is not reloaded and the KV prefix is not broken. | mamidlabs/core/inference.py, mamidlabs/core/settings.py, mamidlabs/ui/main_window.py, mamidlabs/locales/*, tests/test_auto_effort.py |
| 2026-10-18 | **SHA256 verification + resumable downloads for model downloads.** `hf-hub.py` resumes a missing file with `hf_hub_download`, verifies SHA256 once the download finishes (the pinned `sha256` from the catalog or the Hugging Face LFS metadata digest; cached per repo/revision), and deletes the corrupt file on a mismatch. An optional `sha256` was added to `CatalogFile`, and `sha256` + an `mtp` dict to the install payload (the worker also accepts the `mtpRepo` string). | mamidlabs/workers/hf-hub.py, mamidlabs/core/profiles.py, scripts/install-mamidlabs.sh, tests/test_model_download_integrity.py |
| 2026-10-16 | **Release workflow added (`.dmg`).** When a `v*` tag is pushed, the `.dmg` is built with `packaging/macos/build-dmg.sh` and uploaded to the GitHub Release under a **fixed name** (`MamidLabs.dmg`); a "Ready-made package (.dmg)" section and the `releases/latest/download/MamidLabs.dmg` link were added to the README. Branch/PR runs only produce an artifact; the job fails when the tag does not match `__version__`. | .github/workflows/installer.yml, README.md, CHANGELOG.md, AGENTS.md |
| 2026-10-16 | **Setup wizard + hardware measurement + `.dmg` package added; runtime EN/TR localisation wired in.** The Qt6 `QWizard` (13 pages) asks **English or Turkish** on the first page; the choice retranslates live and is written to `settings/api.json:language`. `hwinfo` looks at **unified memory** (Apple Silicon ≥ 32 GB → PRO, ≥ 16 GB → LITE, Intel/little memory → API). `packaging/macos/build-dmg.sh` produces a `.dmg` embedding the wizard (`MamidLabs Setup.app` + embedded sources). `install-mamidlabs.sh` now takes `--language` and writes progress/summary files. i18n wiring was applied to the whole interface, the core (`inference`, `tools`, `settings`) and the CLI; `conftest.py` resets the language state. Tests: `test_hwinfo.py`, `test_wizard.py` (pure), `test_wizard_gui.py` (headless Qt), `test_i18n.py`, `test_packaging_contract.py` (158 in total). | `mamidlabs/core/{i18n,hwinfo}.py`, `mamidlabs/locales/*`, `mamidlabs/wizard/*`, `mamidlabs/ui/*`, `mamidlabs/__main__.py`, `scripts/*`, `packaging/macos/*`, `pyproject.toml`, `conftest.py`, `tests/*`, `README.md`, `CHANGELOG.md` |
| 2026-10-16 | **The macOS edition was written for the first time (1.0.0).** Adapted to macOS based on the Linux port (Python 3.12 + PySide6/Qt6); constants, behaviours and the tool set were kept identical to the Windows edition. Install root `~/Library/Application Support/mamidlabs`; the memory gate uses unified memory (`vm_stat` + `hw.pagesize`, overridable with `MAMIDLABS_FREE_MEM_MIB`) instead of `nvidia-smi`; llama.cpp Metal (macos-arm64/x64); torch from PyPI (MPS), the CUDA index and `nvidia-*` packages removed; transcriber pinned to the CPU on macOS; `run_command` `/bin/zsh`; macOS web User-Agent; PDF fonts macOS + matplotlib DejaVu; 7-Zip Homebrew paths; an `.app` bundle (`Info.plist` + `MacOS-MamidLabs` + PNG→ICNS) instead of `.desktop`; install/manage/uninstall/smoke scripts bash 3.2 compatible; CI `macos-latest`; tests platform-sensitive and new memory tests added. | all |
