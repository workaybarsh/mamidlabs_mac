"""Chat tools: registry, gating and implementations.

Mirrors ``agent/mamidlabs-inference.ps1``'s tool surface. Each tool is a
:class:`ToolSpec` with a JSON schema for the model and a Python handler that
returns a JSON string (the same shape the worker scripts produce).

Gating rules preserved from the Windows edition:

* production tools (image/video/document/chart) are only *offered* when the
  turn's intent allows it, and are checked again at call time,
* ``run_command`` is only offered when the user clearly asks for a command,
* bound-folder tools are only offered when the "agent" chip is on,
* ``read_document`` is only offered when a document is attached,
* web tools disappear after two failed calls with no success (see
  :class:`WebTracker`).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import chart as chart_mod
from . import i18n
from . import providers
from .paths import Paths
from .runner import WorkerRunner
from .settings import Settings

# --- web failure tracking (the "partial failure" fix) ------------------------
_FAILURE_RE = re.compile(
    r"(?i)DNSError|no connections available|cozumlenemedi|ConnectError|basarisiz|"
    r"indirilemedi|timed out|zaman asimi"
)


def classify_web_result(result: object) -> bool:
    """True when a web tool result counts as a *failure*."""
    if result is None:
        return True
    if isinstance(result, dict):
        if not result:
            return True
        if result.get("error"):
            return True
        return False
    text = str(result).strip()
    if not text:
        return True
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
        except ValueError:
            return bool(_FAILURE_RE.search(text))
        return classify_web_result(parsed)
    return bool(_FAILURE_RE.search(text))


class WebTracker:
    """Counts web call outcomes for one turn.

    The note/lock decisions require *no successful call*: a turn that made seven
    web calls with four successes must never be reported as a failed search.
    """

    def __init__(self) -> None:
        self.fail_count = 0
        self.success = False

    def record(self, result: object) -> None:
        if classify_web_result(result):
            self.fail_count += 1
        else:
            self.success = True

    @property
    def unavailable(self) -> bool:
        """Web was attempted and never succeeded."""
        return self.fail_count > 0 and not self.success

    @property
    def should_lock_tools(self) -> bool:
        return self.fail_count >= 2 and not self.success

    def add_failure_note(self, text: str) -> str:
        if self.success:
            return text
        return text + i18n.t("chat.web_failure_note")


# --- tool specs --------------------------------------------------------------
@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict
    kind: str = "read"  # read | write | exec
    handler: Callable[[dict], str] | None = None

    def definition(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": self.parameters}}


def _params(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or []}


def _str(desc: str) -> dict:
    return {"type": "string", "description": desc}


# --- intent detection --------------------------------------------------------
def is_current_info_intent(text: str) -> bool:
    lowered = (text or "").lower()
    markers = ("bugün", "güncel", "son durum", "haber", "hava durumu", "kaç derece",
               "bugünkü", "fiyat", "kur", "dolar", "euro", "borsa", "son dakika",
               "yarın", "bu hafta", "kim kazandı", "seçim", "maç sonucu")
    return any(m in lowered for m in markers)


def is_command_intent(text: str) -> bool:
    lowered = (text or "").lower()
    return any(m in lowered for m in ("komut", "terminal", "çalıştır", "kabuk", "shell",
                                      "bash", "cmd"))


def is_file_intent(text: str) -> bool:
    lowered = (text or "").lower()
    return any(m in lowered for m in ("dosya", "klasör", "dizin", "belge", "oku", "yaz",
                                      "file", "folder", "directory", "document", "read", "write"))


def is_document_intent(text: str) -> bool:
    lowered = (text or "").lower()
    return any(m in lowered for m in ("belge", "pdf", "word", "docx", "rapor", "oluştur",
                                      "yaz", "hazırla", "excel", "sunum", "pptx",
                                      "document", "report", "prepare", "presentation"))


def is_image_intent(text: str) -> bool:
    lowered = (text or "").lower()
    return any(m in lowered for m in ("görsel", "resim", "fotoğraf", "çiz", "image",
                                      "illustrasyon", "logo", "picture", "draw", "photo"))


def is_video_intent(text: str) -> bool:
    lowered = (text or "").lower()
    return any(m in lowered for m in ("video", "animasyon", "klip", "film"))


def is_chart_intent(text: str) -> bool:
    lowered = (text or "").lower()
    return any(m in lowered for m in ("grafik", "chart", "çizelge", "plot", "sütun grafiği",
                                      "pasta grafiği"))


# --- registry ----------------------------------------------------------------
class ToolRegistry:
    def __init__(self, paths: Paths, settings: Settings, runner: WorkerRunner,
                 media: "MediaBridge | None" = None) -> None:
        self.paths = paths
        self.settings = settings
        self.runner = runner
        self.media = media
        self._specs = self._build()

    # --- construction --------------------------------------------------------
    def _build(self) -> dict[str, ToolSpec]:
        return {
            "search_web": ToolSpec(
                "search_web", "Searches the web and returns result titles/summaries.",
                _params({"query": _str("Search query."),
                         "count": {"type": "integer", "description": "Number of results (1-8)."}},
                        ["query"]), handler=self._search_web),
            "fetch_page": ToolSpec(
                "fetch_page", "Reads the text of a web page.",
                _params({"url": _str("Page address (http/https).")}, ["url"]),
                handler=self._fetch_page),
            "find_reference_image": ToolSpec(
                "find_reference_image", "Searches the web for an image and downloads a local reference file.",
                _params({"query": _str("Image search query.")}, ["query"]),
                handler=self._find_reference_image),
            "read_document": ToolSpec(
                "read_document", "Reads a PDF/Word/Excel/PowerPoint/ZIP/RAR document.",
                _params({"path": _str("Document path."),
                         "entry": _str("File name inside the archive (optional).")}, ["path"]),
                handler=self._read_document),
            "read_images_ocr": ToolSpec(
                "read_images_ocr", "Reads images with OCR (extracts text).",
                _params({"paths": {"type": "array", "items": {"type": "string"},
                                   "description": "Image paths."}}, ["paths"]),
                handler=self._read_images_ocr),
            "create_document": ToolSpec(
                "create_document", "Produces a PDF/DOCX/PPTX/XLSX document.",
                _params({"format": _str("pdf|docx|pptx|xlsx"),
                         "title": _str("Document title."),
                         "content": _str("Document content (markdown-like).")},
                        ["format", "content"]), kind="write", handler=self._create_document),
            "generate_chart": ToolSpec(
                "generate_chart", "Produces a chart (bar/line/pie/scatter/function).",
                _params({"type": _str("bar|line|pie|scatter|function"),
                         "title": _str("Chart title."),
                         "labels": {"type": "array", "items": {"type": "string"}},
                         "values": {"type": "array", "items": {"type": "number"}},
                         "expression": _str("Expression for the function type (variable x).")},
                        ["type"]), kind="write", handler=self._generate_chart),
            "generate_image": ToolSpec(
                "generate_image", "Generates/edits an image with the local ComfyUI.",
                _params({"prompt": _str("English image prompt."),
                         "mode": _str("yeni|yeniden_uret|stil_referansi|kimlik_duzenle"),
                         "reference": _str("Reference image path (optional).")},
                        ["prompt"]), kind="write", handler=self._generate_image),
            "generate_video": ToolSpec(
                "generate_video", "Generates a video with the local ComfyUI (Wan 2.2).",
                _params({"prompt": _str("English video prompt."),
                         "mode": _str("metin|gorsel|video"),
                         "reference": _str("Source image/video path (optional).")},
                        ["prompt"]), kind="write", handler=self._generate_video),
            "ask_model": ToolSpec(
                "ask_model", "Asks another API provider a question.",
                _params({"provider": _str("openai|claude|gemini|deepseek|custom"),
                         "prompt": _str("Text to ask."),
                         "model": _str("Model id (optional).")}, ["provider", "prompt"]),
                handler=self._ask_model),
            "list_bound_files": ToolSpec(
                "list_bound_files", "Lists the files in the bound folder.",
                _params({"relative_path": _str("Subfolder (optional).")}),
                handler=self._list_bound_files),
            "read_bound_file": ToolSpec(
                "read_bound_file", "Reads a file in the bound folder.",
                _params({"relative_path": _str("File path.")}, ["relative_path"]),
                handler=self._read_bound_file),
            "search_folder": ToolSpec(
                "search_folder", "Searches the bound folder locally (offline) by keyword and returns "
                "the most relevant text chunks with their file path and line number. Use it on large "
                "folders to find where to look before reading file after file.",
                _params({"query": _str("Search query."),
                         "top_k": {"type": "integer", "description": "Number of results (1-12)."}},
                        ["query"]), handler=self._search_folder),
            "write_bound_file": ToolSpec(
                "write_bound_file", "Writes a file into the bound folder.",
                _params({"relative_path": _str("File path."),
                         "content": _str("Content to write.")}, ["relative_path", "content"]),
                kind="write", handler=self._write_bound_file),
            "run_command": ToolSpec(
                "run_command", "Runs a shell command (user approval required).",
                _params({"command": _str("Command to run.")}, ["command"]),
                kind="exec", handler=self._run_command),
        }

    def all(self) -> dict[str, ToolSpec]:
        return dict(self._specs)

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    # --- gating --------------------------------------------------------------
    def definitions(self, *, chips: dict | None = None, message: str = "",
                    has_documents: bool = False, has_audio: bool = False,
                    profile_lite: bool = False, web: WebTracker | None = None,
                    web_locked: bool = False) -> list[dict]:
        chips = chips or {}
        internet = bool(chips.get("internet", True))
        agent = bool(chips.get("agent", False))
        names: list[str] = []

        if internet and not web_locked:
            names += ["search_web", "fetch_page"]
            if is_image_intent(message) or is_chart_intent(message):
                names.append("find_reference_image")
        if has_documents:
            names.append("read_document")
        if internet:
            names.append("read_images_ocr")
        if is_chart_intent(message):
            names.append("generate_chart")
        if is_image_intent(message):
            names.append("generate_image")
        if is_video_intent(message):
            names.append("generate_video")
        if is_document_intent(message):
            names.append("create_document")
        if agent:
            names.append("ask_model")
            # Bound-folder FILE tools are not offered on a turn with an audio
            # attachment: the audio is already appended to the last user message
            # as a transcript; otherwise the small model tries to search/read/write
            # the AUDIO FILE and wastes turns. If the user explicitly asks for a
            # file (is_file_intent) the tools are offered anyway.
            if not has_audio or is_file_intent(message):
                names += ["list_bound_files", "read_bound_file", "search_folder",
                          "write_bound_file"]
        if is_command_intent(message):
            names.append("run_command")
        return [self._specs[n].definition() for n in names if n in self._specs]

    # --- dispatch ------------------------------------------------------------
    def call(self, name: str, arguments: dict) -> str:
        spec = self._specs.get(name)
        if not spec or not spec.handler:
            return json.dumps({"error": f"unknown tool: {name}"}, ensure_ascii=False)
        try:
            return spec.handler(arguments or {})
        except Exception as exc:  # noqa: BLE001 - surfaced to the model as an error
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)

    # --- web handlers --------------------------------------------------------
    def _agent_tool(self, action: str, **payload) -> dict:
        payload["action"] = action
        return self.runner.run("mamidlabs-agent-tools.py", payload)

    def _search_web(self, args: dict) -> str:
        return json.dumps(self._agent_tool("search_web", query=str(args.get("query", "")),
                                           count=int(args.get("count", 5) or 5)),
                          ensure_ascii=False)

    def _fetch_page(self, args: dict) -> str:
        return json.dumps(self._agent_tool("fetch_page", url=str(args.get("url", ""))),
                          ensure_ascii=False)

    def _find_reference_image(self, args: dict) -> str:
        return json.dumps(self._agent_tool("find_reference_image",
                                           query=str(args.get("query", ""))), ensure_ascii=False)

    # --- documents -----------------------------------------------------------
    def _read_document(self, args: dict) -> str:
        payload = {"action": "read", "path": str(args.get("path", ""))}
        if args.get("entry"):
            payload["entry"] = str(args["entry"])
        return json.dumps(self.runner.run("office-tools.py", payload), ensure_ascii=False)

    def _create_document(self, args: dict) -> str:
        payload = {"action": "create", "format": str(args.get("format", "pdf")),
                   "title": str(args.get("title", "")), "content": str(args.get("content", "")),
                   "outDir": str(self.paths.output_dir("documents"))}
        return json.dumps(self.runner.run("office-tools.py", payload), ensure_ascii=False)

    def _read_images_ocr(self, args: dict) -> str:
        payload = {"action": "ocr", "paths": list(args.get("paths", []))}
        return json.dumps(self.runner.run("ocr-tools.py", payload, env_name="ocr",
                                          timeout=600), ensure_ascii=False)

    # --- charts --------------------------------------------------------------
    def _generate_chart(self, args: dict) -> str:
        return json.dumps(chart_mod.generate_chart(self.paths, args), ensure_ascii=False)

    # --- media ---------------------------------------------------------------
    def _generate_image(self, args: dict) -> str:
        if not self.media:
            return json.dumps({"error": "image generation is not configured in this install."},
                              ensure_ascii=False)
        return json.dumps(self.media.generate_image(args), ensure_ascii=False)

    def _generate_video(self, args: dict) -> str:
        if not self.media:
            return json.dumps({"error": "video generation is not configured in this install."},
                              ensure_ascii=False)
        return json.dumps(self.media.generate_video(args), ensure_ascii=False)

    # --- ask_model -----------------------------------------------------------
    def _ask_model(self, args: dict) -> str:
        provider_id = str(args.get("provider", ""))
        if provider_id in ("", "local"):
            return json.dumps({"error": "ask_model is not used for the local provider."},
                              ensure_ascii=False)
        key = self.settings.provider_key(provider_id)
        model = str(args.get("model") or self.settings.provider(provider_id).get("model") or "")
        if not model:
            return json.dumps({"error": "a model id is required."}, ensure_ascii=False)
        body = {"model": model, "messages": [{"role": "user", "content": str(args.get("prompt", ""))}],
                "max_tokens": 4096}
        try:
            text = providers.stream_completion(provider_id, body, self.settings, key)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
        return json.dumps({"provider": provider_id, "model": model, "text": text},
                          ensure_ascii=False)

    # --- bound folder --------------------------------------------------------
    def _bound_root(self) -> Path | None:
        folder = str(self.settings.get("boundFolder") or "")
        if not folder:
            return None
        return Path(folder).expanduser().resolve()

    def _resolve_bound(self, relative: str) -> Path | None:
        root = self._bound_root()
        if not root:
            return None
        candidate = Path(relative)
        target = candidate if candidate.is_absolute() else (root / relative)
        target = target.resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return None
        return target

    def _list_bound_files(self, args: dict) -> str:
        root = self._bound_root()
        if not root:
            return json.dumps({"error": "no bound folder is configured."}, ensure_ascii=False)
        base = self._resolve_bound(str(args.get("relative_path") or ""))
        if base is None or not base.exists():
            return json.dumps({"error": "the path is outside the bound folder."}, ensure_ascii=False)
        entries = []
        for item in sorted(base.iterdir())[:500]:
            entries.append({"name": item.name, "dir": item.is_dir(),
                            "bytes": item.stat().st_size if item.is_file() else 0})
        return json.dumps({"root": str(base), "entries": entries}, ensure_ascii=False)

    def _read_bound_file(self, args: dict) -> str:
        target = self._resolve_bound(str(args.get("relative_path", "")))
        if target is None or not target.is_file():
            return json.dumps({"error": "file not found or outside the bound folder."},
                              ensure_ascii=False)
        if target.stat().st_size > 2 * 1024 * 1024:
            return json.dumps({"error": "the file is too large (2 MB limit)."}, ensure_ascii=False)
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
        return json.dumps({"path": str(target), "text": text[:60000]}, ensure_ascii=False)

    def _search_folder(self, args: dict) -> str:
        root = self._bound_root()
        if not root or not root.is_dir():
            return json.dumps({"error": "no bound folder is configured."}, ensure_ascii=False)
        query = str(args.get("query", "")).strip()
        if not query:
            return json.dumps({"error": "query is required."}, ensure_ascii=False)
        try:
            top = int(args.get("top_k", 6) or 6)
        except (TypeError, ValueError):
            top = 6
        top = max(1, min(12, top))
        payload = {"action": "search", "root": str(root), "query": query,
                   "top": top, "store": str(self._rag_store(root))}
        result = self.runner.run("rag-tools.py", payload, timeout=180)
        if not isinstance(result, dict) or result.get("error"):
            message = result.get("error") if isinstance(result, dict) else str(result)
            return f"Search error: {message}"
        hits = result.get("hits") or []
        files = result.get("files", 0)
        chunks = result.get("chunks", 0)
        if not hits:
            note = result.get("message") or "No matches."
            return f"{note} ({files} files, {chunks} chunks scanned)"
        blocks = [f"[{hit.get('path')}:{hit.get('line')}]\n{hit.get('text')}"
                  for hit in hits]
        return (f"Most relevant chunks for '{query}' in the bound folder "
                f"({files} files, {chunks} chunks scanned):\n\n" + "\n\n".join(blocks))

    def _rag_store(self, root: Path) -> Path:
        """RAG index path under ``tools/rag`` (bound-<hash8>.json).

        The path is hashed as-is. macOS volumes are usually case-insensitive but
        the string is kept verbatim (mirrors the Linux edition, whose paths are
        case-sensitive).
        """
        tag = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:8]
        return self.paths.rag / f"bound-{tag}.json"

    def _write_bound_file(self, args: dict) -> str:
        target = self._resolve_bound(str(args.get("relative_path", "")))
        if target is None:
            return json.dumps({"error": "the path is outside the bound folder."}, ensure_ascii=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(args.get("content", "")), encoding="utf-8")
        return json.dumps({"path": str(target), "bytes": target.stat().st_size},
                          ensure_ascii=False)

    # --- command -------------------------------------------------------------
    def _run_command(self, args: dict) -> str:
        command = str(args.get("command", "")).strip()
        if not command:
            return json.dumps({"error": "the command is empty."}, ensure_ascii=False)
        workdir = self._bound_root() or self.paths.root
        shell = "/bin/zsh" if sys.platform == "darwin" else "/bin/bash"
        try:
            completed = subprocess.run(  # noqa: S602 - user-approved command
                [shell, "-lc", command], capture_output=True, text=True,
                timeout=120, cwd=str(workdir),
            )
        except subprocess.TimeoutExpired:
            return json.dumps({"error": "the command timed out (120 s)."}, ensure_ascii=False)
        except OSError as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
        return json.dumps({"exit_code": completed.returncode,
                           "stdout": completed.stdout[-20000:],
                           "stderr": completed.stderr[-8000:]}, ensure_ascii=False)


@dataclass
class MediaBridge:
    """Adapter the UI supplies so media tools can drive ComfyUI/API generation."""

    generate_image: Callable[[dict], dict] = field(default=lambda a: {"error": "none"})
    generate_video: Callable[[dict], dict] = field(default=lambda a: {"error": "none"})


def parse_command(command: str) -> list[str]:
    """Split a command for display/logging (never for execution)."""
    try:
        return shlex.split(command)
    except ValueError:
        return [command]


def sanitize_name(value: str, fallback: str = "file") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")
    return cleaned or fallback


__all__ = [
    "ToolSpec", "ToolRegistry", "WebTracker", "MediaBridge", "classify_web_result",
    "is_current_info_intent", "is_command_intent", "is_file_intent", "is_document_intent",
    "is_image_intent", "is_video_intent", "is_chart_intent",
]
