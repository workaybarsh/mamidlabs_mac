# MamidLabs — macOS

A fully **local**, multimodal AI workspace. In a single Qt6 window it offers chat, web
search, document reading/creation, OCR, image understanding, image generation, photo
editing, video generation, chart drawing and audio transcription. The language model runs
on **llama.cpp** (`llama-server`), the image/video models on **ComfyUI**, using the Mac's
**Metal** accelerator (llama.cpp Metal; torch/ComfyUI MPS). OpenAI, Claude, Gemini,
DeepSeek and custom OpenAI-compatible endpoints are optional API providers.

This repository is the **macOS port** of the Windows edition (`MamidLabsTR` /
`MamidLabsENG`). Since WinForms/PowerShell do not run on macOS, the application is written
in a single language (**Python 3.12 + PySide6/Qt6**); it uses the same engines (llama.cpp,
ComfyUI) and the same Python tools (web, document, OCR, media, transcription).

Repository: `github.com/workaybarsh/mamidlabs_mac` · Default install root:
`~/Library/Application Support/mamidlabs` (changed with `MAMIDLABS_ROOT`).

---

## Features

| Capability | How it works |
|---|---|
| Chat (streaming) | Local `llama-server` (llama.cpp, Metal) or an API provider; thinking and answer are shown separately |
| Web search / page reading | `ddgs` + page extraction; **never invents when it fails**, reports honestly |
| Document reading / creation | Reads PDF, Word, Excel, PowerPoint, ZIP, RAR; creates PDF/DOCX/PPTX/XLSX |
| OCR | PaddleOCR (CPU) — optional component |
| Image understanding | Reads images with the model's vision projector (mmproj) |
| Image generation / editing | Local ComfyUI (Krea-2 Turbo, MPS; identity editing MAX/FLASH) or API |
| Video generation | Local ComfyUI (Wan 2.2 TI2V 5B) or API |
| Chart drawing | matplotlib; bar/line/pie/scatter/function (safe expression evaluator) |
| Audio transcription | faster-whisper `large-v3-tr` + AST sound events + optional speaker diarisation (CPU) |
| Tool calling | `search_web`, `fetch_page`, `read_document`, `create_document`, `generate_image`, `generate_video`, `generate_chart`, `ask_model`, bound-folder tools, `run_command` |
| Approval flow | Write/execute tools ask for user permission; not asked when the "Full access" chip is on |
| API providers | openai, claude, gemini, deepseek, custom (OpenAI-compatible) |

**Safety behaviour (same as the Windows edition):** no document/image/video/chart is
produced unasked; if the web search fails or current information is requested while the
Internet is off, the model says so explicitly **instead of inventing**; `read_document` is
only offered when there is a document context.

---

## Requirements

- **macOS 12 (Monterey)** or later — Apple Silicon (arm64) recommended; Intel x86-64 supported
- **Python 3.11–3.13** (3.12 recommended; `brew install python@3.12`), `git`, `curl`, `unzip`
- **Homebrew** (optional but recommended: `brew install sevenzip` for RAR, `python@3.12`)
- A Metal-capable GPU (present on all supported Macs). **32 GB** unified memory is recommended
  for the 27B profile, **16 GB** for LITE.
- Disk: **LITE ~36 GB**, **MAX/FLASH ~52 GB** (models + ComfyUI + environments)

> **Unified memory note:** macOS has no separate VRAM; the GPU shares the system memory.
> The memory gate therefore computes **reclaimable unified memory** (`vm_stat`) and does
> not use `nvidia-smi`.

---

## Installation

### Ready-made package (.dmg)

Download the `.dmg` package of the latest release directly:

- **Download:** [`MamidLabs.dmg`](https://github.com/workaybarsh/mamidlabs_mac/releases/latest/download/MamidLabs.dmg)

Open the DMG, drag the **MamidLabs Setup** app into the `Applications` folder, then run it.

### Setup wizard (recommended)

Open `MamidLabs-Setup-<version>.dmg` and drag the **MamidLabs Setup** app into the
`Applications` folder. The wizard measures the hardware and suggests a suitable profile:

> language (English / Türkçe) → welcome → licence → install folder → hardware report →
> profile (LITE / PRO / download later / own model–API) → (your own models) →
> (API) → (components) → ready → install → summary → finish

The wizard writes the language choice into `settings/api.json`, saves your own model paths
and component choices, and leaves the real work to `scripts/install-mamidlabs.sh`; it reads
progress from `logs/kurulum-adim.txt`.

You can also build the DMG yourself:

```bash
packaging/macos/build-dmg.sh    # packaging/macos/Output/MamidLabs-Setup-<version>.dmg
./scripts/mamidlabs-setup.sh    # open the wizard directly from source
```

Details: [`packaging/macos/README.md`](packaging/macos/README.md).

### From the terminal

```bash
git clone https://github.com/workaybarsh/mamidlabs_mac.git
cd mamidlabs_mac
./scripts/install-mamidlabs.sh --profile flash --language en
```

Install stages: `preflight → layout → llama → python → comfyui → models → verify`.
Use `--stage` to run them individually; for example, to refresh only the program files:

```bash
./scripts/install-mamidlabs.sh --stage layout
```

Useful options:

| Option | Effect |
|---|---|
| `--root <path>` | Install root (default `~/Library/Application Support/mamidlabs`) |
| `--profile max\|flash\|lite` | Model download profile (default: downloads nothing) |
| `--language en\|tr` | Interface language; written to `settings/api.json` |
| `--skip-media` | Skip ComfyUI and the image/video components |
| `--skip-audio` | Skip the transcription environment (`venv/asr`) |
| `--skip-ocr` | Skip the OCR environment (`venv/ocr`) |
| `--skip-models` | Skip the language model download |
| `--no-desktop` | Do not install the `MamidLabs.app` bundle |
| `--force` | Reinstall over the existing install |

Install root layout:

```
~/Library/Application Support/mamidlabs/
  llama.cpp/<build>/llama-server   pinned llama.cpp build (Metal)
  models/                          GGUF language models (+ mmproj)
  ComfyUI/                         pinned ComfyUI commit + models/
  venv/{app,imagegen,asr,ocr}/     Python environments (one per concern)
  tools/{hf-home,downloads,pip-cache}/
  settings/api.json                all user settings (secrets 0600)
  chats/  outputs/  logs/          chats, generated files, logs
  mamidlabs-launch                 launcher (the script the .app bundle calls)
```

The installer also creates the `~/Applications/MamidLabs.app` bundle (the icon is generated
as `.icns`); it can be started from Finder/Dock/Launchpad.

---

## Usage

Start the application:

```bash
~/Library/Application\ Support/mamidlabs/mamidlabs-launch
```

Or **Launchpad / Finder → Applications → MamidLabs** (the installer places the
`MamidLabs.app` bundle under `~/Applications`).

Model management:

```bash
./scripts/manage-mamidlabs.sh start flash    # start the local model
./scripts/manage-mamidlabs.sh stop           # stop
./scripts/manage-mamidlabs.sh status         # active profile
./scripts/manage-mamidlabs.sh comfy          # start ComfyUI (for media)
./scripts/manage-mamidlabs.sh closecomfy     # close an idle ComfyUI
./scripts/manage-mamidlabs.sh doctor         # inspect the installation
./scripts/manage-mamidlabs.sh profiles       # profile status
```

Command line (without the GUI):

```bash
python -m mamidlabs doctor
python -m mamidlabs profiles --json
python -m mamidlabs manage start --profile lite
```

---

## Uninstalling

```bash
./scripts/uninstall-mamidlabs.sh                  # everything (asks)
./scripts/uninstall-mamidlabs.sh --keep-user-data # keeps settings/chats/models
./scripts/uninstall-mamidlabs.sh --dry-run        # only show
```

The uninstaller only touches the install root and the `~/Applications/MamidLabs.app`
bundle; it deletes nothing outside the root.

---

## Hardware facts

On macOS speed depends on Metal and on the amount of unified memory. The numbers below are
a **reference** from the Windows/NVIDIA edition; on Apple Silicon the chat token rate is
usually similar, while image/video generation (MPS) is slower than CUDA.

| | 32 GB (27B MAX/FLASH) | 16 GB (9B LITE) |
|---|---|---|
| Chat | smooth on Metal (MTP on) | smooth on Metal (MTP on) |
| Image (`new`) | on the order of minutes (MPS) | on the order of minutes (MPS) |
| Photo editing (`identity_edit`) | supported | **not supported** (not enough memory) |
| Audio transcription | CPU (int8) | CPU (int8) |

By default ComfyUI runs **only during media generation** and is closed before the language
model loads (it holds neither memory nor GPU while idle).

---

## Tests

```bash
python3 -m pip install pytest -r requirements/app.txt
python3 -m pytest -q          # 203 tests; PySide6 is not required (Qt is only needed for the wizard tests)
```

If PySide6 is installed, the wizard window is also tested headlessly
(`QT_QPA_PLATFORM=offscreen`); otherwise those tests are skipped. End-to-end verification
(on an installed root, with real models):

```bash
./scripts/smoke-test.sh --profile flash
```

---

## Contributing and development

**[AGENTS.md](AGENTS.md)** explains how the codebase is started, how the parts talk to each
other, and the known pitfalls. When you add a feature, also update `AGENTS.md` and
`CHANGELOG.md` in the same commit.

---

## Licence

The MamidLabs source code is licensed under the **PolyForm Strict License 1.0.0**
(source-available; **noncommercial** use only). You may not distribute, modify, or make new
works based on the software; commercial use requires prior written permission from the
Licensor. Copyright belongs to Aybars Haydar Altuntaş. For details, see the [LICENSE](LICENSE)
file and https://polyformproject.org/licenses/strict/1.0.0.
The models used (Qwen, Krea 2, Krea 2 Identity Edit LoRA, Wan 2.2 etc.) and third-party
components (llama.cpp, ComfyUI, ComfyUI-GGUF, comfyui-krea2edit etc.) are subject to their own
licenses; this licence does not cover them.
