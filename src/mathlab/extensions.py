from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any


class ExtensionRegistry:
    """Hot-loadable project-local capabilities.

    The RA writes executable Python tools into .mathlab/extensions and updates manifest.json.
    Every list/run operation re-reads the manifest, so workers see new capabilities without restarting.
    Extension programs receive a JSON object on stdin and must print JSON (or text) on stdout.
    """

    def __init__(self, project_dir: Path):
        self.root = project_dir / ".mathlab" / "extensions"
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest = self.root / "manifest.json"
        if not self.manifest.exists():
            self.manifest.write_text('{"tools": {}}\n', encoding="utf-8")

    def tools(self) -> dict[str, dict[str, Any]]:
        try:
            data = json.loads(self.manifest.read_text(encoding="utf-8"))
            return dict(data.get("tools", {}))
        except (json.JSONDecodeError, OSError):
            return {}

    async def run(self, name: str, args: dict[str, Any], timeout_s: int = 300) -> dict[str, Any]:
        tool = self.tools().get(name)
        if not tool:
            return {"ok": False, "error": f"Unknown extension {name!r}"}
        rel = tool.get("entrypoint")
        if not rel:
            return {"ok": False, "error": "Extension has no entrypoint"}
        script = (self.root / rel).resolve()
        if self.root.resolve() not in script.parents:
            return {"ok": False, "error": "Entrypoint escapes extension directory"}
        if not script.exists():
            return {"ok": False, "error": f"Missing entrypoint: {script.name}"}
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(script),
            cwd=str(self.root),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        payload = json.dumps(args).encode()
        try:
            out, err = await asyncio.wait_for(proc.communicate(payload), timeout=timeout_s)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return {"ok": False, "error": "Extension timed out"}
        text = out.decode(errors="replace")
        try:
            value: Any = json.loads(text)
        except json.JSONDecodeError:
            value = text
        return {"ok": proc.returncode == 0, "result": value, "stderr": err.decode(errors="replace")[-4000:]}
