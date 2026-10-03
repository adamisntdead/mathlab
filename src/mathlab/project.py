from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from .config import EXAMPLE_CONFIG
from .db import Blackboard


def new_id(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def init_project(destination: Path, handoff: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    if not handoff.exists():
        raise FileNotFoundError(handoff)
    # Normalize the one required research handoff into text. Preserve a PDF original for citation/context.
    suffix = handoff.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(handoff))
        pages = []
        for i, page in enumerate(reader.pages, 1):
            pages.append(f"\n\n--- SOURCE PDF PAGE {i} ---\n\n" + (page.extract_text() or ""))
        (destination / "HANDOFF.md").write_text("".join(pages), encoding="utf-8")
    else:
        try:
            text = handoff.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Handoff must be Markdown/text/TeX or PDF") from exc
        (destination / "HANDOFF.md").write_text(text, encoding="utf-8")
    for name in ["references", "code", "data", "artifacts"]:
        (destination / name).mkdir(exist_ok=True)
    if suffix == ".pdf":
        shutil.copy2(handoff, destination / "references" / handoff.name)
    internal = destination / ".mathlab"
    for name in ["workspaces", "extensions", "logs"]:
        (internal / name).mkdir(parents=True, exist_ok=True)
    manifest = internal / "extensions" / "manifest.json"
    if not manifest.exists():
        manifest.write_text('{"tools": {}}\n', encoding="utf-8")
    cfg = destination / "mathlab.toml"
    if not cfg.exists():
        cfg.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    Blackboard(internal / "state.sqlite").event("project.initialized", "system", {"handoff": str(handoff)})
    return destination


def read_handoff(project_dir: Path, max_chars: int | None = None) -> str:
    path = project_dir / "HANDOFF.md"
    text = path.read_text(encoding="utf-8", errors="replace")
    if max_chars and len(text) > max_chars:
        return text[:max_chars] + "\n\n[HANDOFF TRUNCATED BY CONFIG]"
    return text


def ensure_workspace(project_dir: Path, agent_id: str) -> Path:
    ws = project_dir / ".mathlab" / "workspaces" / agent_id
    ws.mkdir(parents=True, exist_ok=True)
    return ws
