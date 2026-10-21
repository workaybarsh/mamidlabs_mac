# Installation guide (macOS)

This guide explains how to install, start, update and uninstall MamidLabs on macOS. For
detailed technical information see [technical-notes.md](technical-notes.md).

## 1. Prerequisites

| Requirement | Note |
|---|---|
| macOS 12 (Monterey)+ | Apple Silicon (arm64) recommended; Intel x86-64 supported |
| Python 3.11–3.13 | 3.12 recommended. `brew install python@3.12` |
| `git`, `curl`, `unzip` | For the ComfyUI and llama.cpp downloads (ship with macOS) |
| Homebrew | `brew install python@3.12 sevenzip` (sevenzip for RAR, optional) |
| Metal GPU | Present on all supported Macs. **32 GB** unified memory recommended for the 27B profile, **16 GB** for LITE |
| Disk | LITE ~36 GB, MAX/FLASH ~52 GB |

If Homebrew is not installed:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python@3.12
```

> **Unified memory:** macOS has no separate VRAM; the GPU shares the system memory.
> The memory gate measures reclaimable unified memory with `vm_stat`.

## 2. Installation

```bash
git clone https://github.com/workaybarsh/mamidlabs_mac.git
cd mamidlabs_mac
./scripts/install-mamidlabs.sh --profile flash
```

If you do not pass `--profile`, the program files and engines are installed but **no
language model is downloaded**; you can later check the status and download with
`./scripts/manage-mamidlabs.sh profiles`.

### Stages

The installer runs these stages in order (selectable with `--stage`):

| Stage | What it does |
|---|---|
| `preflight` | Python/git/disk/Metal/7-Zip checks |
| `layout` | `venv/app`, application bundle, launcher, `MamidLabs.app` + `.icns` icon |
| `llama` | Downloads the pinned `llama.cpp` (`b10998`) Metal `llama-server` |
| `python` | `venv/imagegen`, `venv/asr`, `venv/ocr` environments (torch PyPI/MPS) |
| `comfyui` | Pinned commit ComfyUI + `ComfyUI-GGUF` + `comfyui-krea2edit` |
| `models` | Downloads the language model + mmproj when `--profile` is given |
| `verify` | Inspects the installation (`python -m mamidlabs doctor`) |

Examples:

```bash
# Refresh only the program files (update)
./scripts/install-mamidlabs.sh --stage layout

# Lightweight install without media/audio/OCR
./scripts/install-mamidlabs.sh --profile lite --skip-media --skip-ocr

# Install to a different root
./scripts/install-mamidlabs.sh --root "$HOME/mamidlabs" --profile max
```

## 3. First run

```bash
~/Library/Application\ Support/mamidlabs/mamidlabs-launch
```

or **Launchpad / Finder → Applications → MamidLabs** (the installer creates the
`~/Applications/MamidLabs.app` bundle).

On first launch:

1. Pick the profile from the **Profile** box at the top (MAX / FLASH / LITE).
2. Press the **Start model** button; wait until the status bar says "Ready".
3. Type your message and press **Send** (or `⌘+Enter`).

### Chips

| Chip | When on |
|---|---|
| **Internet** | Web search and page reading tools are offered |
| **Agent** | Bound-folder tools and `ask_model` are offered |
| **Full access** | No approval is asked for write/execute tools |

## 4. API providers (optional)

Menu → **API connections…**. Pick one of the openai / claude / gemini / deepseek / custom
rows and enter the key. Keys are stored preferably in the **macOS login keychain**
(Keychain), otherwise in `settings/api.json` with `0600` permissions. `custom` is your own
OpenAI-compatible endpoint (Ollama, LM Studio, vLLM…); enter the base URL, the key is
optional.

## 5. Management

```bash
./scripts/manage-mamidlabs.sh start [max|flash|lite]  # start the model
./scripts/manage-mamidlabs.sh stop                    # stop
./scripts/manage-mamidlabs.sh status                  # active profile
./scripts/manage-mamidlabs.sh comfy                   # start ComfyUI
./scripts/manage-mamidlabs.sh closecomfy              # close the idle ComfyUI
./scripts/manage-mamidlabs.sh doctor                  # installation check
./scripts/manage-mamidlabs.sh profiles                # profile status
```

## 6. Updating

1. Close the application.
2. Pull the repository: `git pull`
3. Refresh the program files: `./scripts/install-mamidlabs.sh --stage layout`

User data (`settings/`, `chats/`, `models/`, `outputs/`) is preserved.

## 7. Uninstalling

```bash
./scripts/uninstall-mamidlabs.sh                  # everything (asks for confirmation)
./scripts/uninstall-mamidlabs.sh --keep-user-data # keeps settings/chats/models
./scripts/uninstall-mamidlabs.sh --dry-run        # only show
```

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| "PySide6 not found" | `./scripts/install-mamidlabs.sh --stage layout` |
| "Not enough unified memory" | Close other applications; switch to the LITE profile |
| The model does not load | `python -m mamidlabs doctor`; check the logs in `logs/` |
| Image generation does not work | `./scripts/manage-mamidlabs.sh comfy`; ComfyUI logs: `logs/comfyui.*.log` |
| ComfyUI is very slow | MPS is used on macOS (slower than CUDA); some custom nodes run on the CPU |
| Transcription fails | Is `venv/asr` installed? It may have been skipped with `--skip-audio` (runs on the CPU on macOS) |
| Web search does not work | Turn on the Internet chip; when offline the model does not invent, it says so |
| `bash: bad substitution` | The scripts are bash 3.2 compatible; do not run them in a different shell |

Logs are under `~/Library/Application Support/mamidlabs/logs/`:
`llama-server-*.std{out,err}.log`, `comfyui.{out,err}.log`, `audit.jsonl`,
`smoke-test-son.json`.
