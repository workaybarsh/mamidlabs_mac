# Technical notes (macOS)

This document summarises the design decisions and measured behaviour of the MamidLabs macOS
edition. For the developer guide see [AGENTS.md](../AGENTS.md).

## 1. Why it was rewritten from scratch

The Windows edition is written in **PowerShell 7 + WinForms**; neither exists on macOS. That
is why the macOS edition was written in a single language (Python 3.12 + PySide6/Qt6).
The architecture, constants and behaviour were, however, kept **exactly** the same as the
Windows edition, so all three editions behave the same way and use the same models.

**Reused:** platform-independent Python workers (web search, document I/O, OCR, media,
transcription, `mtp_inject`, `hf-hub`, `api-media`). They keep the one-shot JSON
stdin/stdout contract and each runs in its own virtual environment.

## 2. Install root and path independence

The install root follows the macOS convention:
`~/Library/Application Support/mamidlabs`; `MAMIDLABS_ROOT` overrides everything. (On
non-macOS hosts/tests it falls back to XDG.)

Workers **do not derive the root from their own location** (the package lives inside
`site-packages`). `mamidlabs/workers/_root.py` reads the root from `MAMIDLABS_ROOT` first,
otherwise from the Library default. `WorkerRunner` passes `MAMIDLABS_ROOT` and `HF_HOME` to
every child process, so the audio models are found offline in the install root's HF cache.

## 3. Processes and ports

| Process | Port | Owner |
|---|---|---|
| `llama-server` | 8080 | `mamidlabs/core/manage.py` (`ModelManager`) |
| ComfyUI (`venv/imagegen`) | 8188 | media bridge / `manage-mamidlabs.sh comfy` |
| Transcription worker (`venv/asr`) | random, 127.0.0.1 only | `mamidlabs/core/inference.py` |

Model start/stop is serialised with `manage.FileLock` (`fcntl` on POSIX, `msvcrt` on
Windows — the tests can be imported on Windows too).

Process discovery is portable: `ps -ww -eo pid=,ppid=,args=` (macOS/Linux). The executable
path is only read from `/proc/<pid>/exe` on Linux; on macOS root matching uses the full
command line. The port listener is found via `/proc` on Linux and via `lsof` on macOS.

## 4. Profiles and server arguments

The profile catalog lives in `mamidlabs/core/profiles.py`; the aliases (`PROFILE_ALIASES`)
are the same as in the Windows edition:

| Profile | Alias | Important flags |
|---|---|---|
| MAX | `qwen3.8-27b-max` | ctx 32768, predict 8192, gpu-layers 99, q4_0 KV, cache-reuse 256, batch 512/256, threads 6/12, `--mmproj --no-mmproj-offload --image-min-tokens 1024`, `--reasoning-effort xhigh`, `--spec-type draft-mtp` when MTP is present |
| FLASH | `qwen3.8-27b-flash` | the same files; `--reasoning-effort low` |
| LITE | `qwen3.5-9b-lite` | ctx `liteContext` (32768), predict 8192, batch 256/128, threads 4/8, `--image-min-tokens 512`, `--reasoning-effort low`, `--spec-type draft-mtp` when MTP is present |

The server arguments are **exactly the same** as in the Windows edition; on macOS Metal is
the default backend (`--gpu-layers 99` applies to Metal too), no extra flag is needed. Since
MAX and FLASH use the same files, they appear as a single "Qwen3.8 MAX" entry in the
interface (`catalog_for_display`); switching happens from the bottom bar. Lookup by id uses
the full catalog (`get_profile`).

**MTP (Multi-Token Prediction).** `--spec-type draft-mtp` is only added when the GGUF
actually carries MTP/`nextn` layers (`manage.gguf_has_mtp`). LITE's 9B GGUF loses this header
during conversion; it is added back with `mtp_inject.py` during the download. No separate
draft model is needed and the output is lossless. Disable it with
`settings/api.json → mtp=false`.

**Auto effort (MAX/FLASH).** MAX and FLASH are the same model; the only difference is the
server's `--reasoning-effort` value. Because changing profile reloads the model (~15 s), by
default the effort is given **per request** (`inference.auto_reasoning_effort` →
`chat_template_kwargs.reasoning_effort`): a short question/greeting `low`, medium `medium`,
multi-step maths/code/analysis/comparison `xhigh`. The choice is made **once per turn** and
stays fixed for the whole turn (the system prefix does not change, so the KV cache is not
broken). It can be turned off (`settings/api.json → autoEffort`, Profiles menu). LITE's
template ignores this key; the field is not sent to API providers.

**Download and verification.** `hf-hub.py` verifies the size against `bytes`, **resumes**
the missing file with `hf_hub_download`, and verifies **SHA256** once the download finishes:
the pinned `sha256` from the catalog when present, otherwise the `lfs.sha256` digest in the
Hugging Face LFS metadata (cached per repo/revision). If the digest does not match, the
corrupt file is **deleted**; verification happens **before** MTP injection because the
injection changes the file. `HF_HOME` is under the root.

**Memory gate.** Needed = model file + headroom. MAX/FLASH headroom **750 MiB** (tolerance 0:
an error when available < needed), LITE headroom **300 MiB** (tolerance 1024 MiB: a warning
in `[needed-1024, needed)`). The vision projector is on the CPU in all three profiles
(`--no-mmproj-offload`) and does not count against the budget. Before the model loads, the
application's orphan GPU workers (idle audio/OCR workers) are stopped
(`stop_orphan_workers`).

**Measurement on macOS.** There is no separate VRAM. `manage.available_memory_mib()` returns
reclaimable unified memory: the **free + inactive + speculative + purgeable** pages from
`vm_stat` are summed and multiplied by `hw.pagesize`. "Pages free" alone is **not used**
(macOS deliberately keeps a large file cache; used alone, the model would never load).
`macos_total_mib()` returns the total memory for information. `MAMIDLABS_FREE_MEM_MIB`
overrides the measurement (tests and manual tuning). On non-macOS hosts `nvidia-smi` and
`/proc/meminfo` are tried in that order.

## 5. ComfyUI lifecycle

ComfyUI runs **only during media generation**; it is closed when the job ends and before the
language model loads (it holds neither memory nor GPU while idle). With
`comfyKeepAlive=true` it can be kept open between media jobs on LITE. Leaked/duplicate
instances are counted by process **roots** (ComfyUI is a process pair); the single instance
listening on `:8188` is kept.

On macOS ComfyUI runs with **MPS**; the torch in `venv/imagegen` is the PyPI wheel (MPS built
in), no CUDA index is used.

## 6. API providers

There is a single table in `providers.py`: `openai`, `claude`, `gemini`, `deepseek`,
`custom`. `custom` is the user's OpenAI-compatible endpoint; the key is optional (when empty
no `Authorization` header is sent).

- **Claude converter:** translates the OpenAI chat format to the Claude Messages API and back.
  No `thinking` field is sent; `tool_choice` is sent as `auto` only when present in the body;
  the `max_tokens` floor is 16000. In the tool loop, signed `thinking` blocks are collected by
  `ClaudeStream` and sent back through the first `tool_use` id without changing their order
  (in memory only).
- **DeepSeek** does not accept images; `image_url` parts are flattened into a text note.
- Keys are stored preferably in the macOS login keychain (Keychain / `keyring`), otherwise in
  `settings/api.json` with `0600` permissions (`Settings.secret_backend` reports which is in
  use).

## 7. Chat flow and context

- The system prompt is fixed (`SYSTEM_PROMPT`); turn-specific hints are added **to the start
  of the last user message**, not to the system prompt — this way the server's KV cache prefix
  is not broken.
- The `done` event also carries the `assistant.tool_calls` and `tool` messages added in that
  turn; the interface appends them to the persistent history (otherwise the client prefix in
  the next turn would differ from the server's and the context would be processed again from
  scratch).
- Context protection has **two passes**: when the prompt + `max_tokens` + headroom would
  exceed the context at the start of a turn, `compact_turn_messages` first keeps only the head
  of the oldest tool outputs, and if that is not enough it replaces the oldest tool outputs
  and old assistant text with a short marker. **If the prompt still does not fit**, tools are
  not offered and the model is asked to answer from the findings present, with `max_tokens`
  reduced to the remaining room (because of `llama-server --no-context-shift` an overflowing
  prompt is a hard error). If nothing was shortened, no "compacted" note is shown; the
  `assistant.tool_calls`/`tool` pairing is never broken.

### Web failure honesty

If **none** of the web calls made in a turn succeeded
(`WebTracker.unavailable = fail_count > 0 and not success`), the model is given an "no
internet" note and invention is blocked on a turn that asks for current information.
**Partial success** (for example 4 of 7 calls succeed) is **not** counted as a failure; the
answer is based on a real source and invented "Source:"/URL lines are stripped
(`strip_fabricated_citations`).

## 8. Tool gates

Production tools (image/video/document/chart) are **offered** only when there is intent and
are checked again **at call time**. `run_command` is only offered when the user explicitly
asks for a command (`/bin/zsh -lc`); bound-folder tools (`list_bound_files`,
`read_bound_file`, `search_folder`, `write_bound_file`) only when the "Agent" chip is on;
`read_document` only when there is a document context. Web tools lock after ≥2 failures with
no successful call. On a turn with an audio attachment, the bound-folder **file** tools are
not offered to the model (the audio is already transcribed; if the user explicitly asks for a
file they are offered anyway).

### Untrusted content and approval (prompt injection)

Web/document/OCR/bound-file content is **data**, not instructions. The results of
`search_web`, `fetch_page`, `read_document`, `read_images_ocr`, `read_bound_file` and
`search_folder` are given to the model with the `chat.untrusted_prefix` label; the fixed
system prompt (`prompt.untrusted`) says that phrases in the content such as "ignore previous
instructions" or "run this command" must **not be applied**. If untrusted content was read in
that turn, `approval_required` makes `run_command` and `write_bound_file` ask for approval
**even with the "Full access" chip on**; the approval dialog also states the reason
(`chat.approval_untrusted`). This way an instruction hidden in a page cannot make the app act
on the user's behalf.

### Local RAG: offline search in the bound folder

The `search_folder` tool finds the relevant text chunks in a large folder before reading files
one by one. The worker `rag-tools.py` (no extra package) scans only plain-text extensions,
skips heavy folders such as `node_modules`/`venv`/`.git`, produces ~900-character chunks while
preserving line boundaries, and ranks them with BM25 (k1=1.2, b=0.75) + an exact-phrase bonus;
the result is returned as `path:line` + chunk text. The index is kept in
`tools/rag/bound-<hash>.json` and is not rebuilt while the file signature (path+size+mtime)
is unchanged; a corrupt index is rebuilt silently. The result is also labelled as untrusted
content.

## 9. Chart drawing

`chart.py` uses matplotlib (the counterpart of `System.Drawing` on Windows). For the
`function` type the expression is evaluated with a **safe AST evaluator** instead of `eval`
(only numbers, `x`, allowed functions and operators). The result is shown in the chat and
saved under `outputs/charts`.

## 10. Audio transcription

The engine is `faster-whisper large-v3-tr` + AST sound events + optional pyannote speaker
diarisation. The output is **chronological and without timestamps**:
`(footsteps)` / `Speaker: ...` lines. Sound events are **on** by default
(`settings/api.json → audioEvents`).

On macOS CTranslate2 has no Metal backend; the pipeline **runs on the CPU (int8)**. Device
selection therefore short-circuits: `config.choose_plan` always returns `('cpu', False)` on
macOS (no language-model swap is needed). `available_ram_mib` and `total_vram_mib` use the
unified-memory measurement on macOS.

## 11. Hardware facts

On macOS speed depends on Metal and on the amount of unified memory. The NVIDIA measurements
(Windows/Linux) are a reference.

| | 32 GB unified memory (MAX/FLASH) | 16 GB unified memory (LITE) |
|---|---|---|
| Chat | smooth on Metal (MTP on) | smooth on Metal (MTP on) |
| Image (`new`) | on the order of minutes (MPS) | on the order of minutes (MPS) |
| Photo editing | supported | **not supported** |
| Audio transcription | CPU (int8) | CPU (int8) |

The 27B model occupies ~15 GB of the GPU/GPU-like budget (the file is ~14.6 GB, plus the
q4_0 KV cache + compute buffers + the MTP draft context); that is why the MAX/FLASH headroom
is 750 MiB: the model only loads if it fits **completely** and then uses **all available
memory**.
