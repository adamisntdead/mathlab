"""Dependency-free smoke check for MathLab persistence and hot extensions."""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from mathlab.db import Blackboard
from mathlab.extensions import ExtensionRegistry
from mathlab.project import init_project


async def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        handoff = root / "handoff.md"
        handoff.write_text("# Test\nInvestigate X.", encoding="utf-8")
        project = init_project(root / "project", handoff)
        db = Blackboard(project / ".mathlab" / "state.sqlite")
        db.create_task("T1", "task", "desc", "EXPLORE", "island", 0.8, "smoke")
        assert db.open_tasks()[0]["id"] == "T1"
        db.create_claim("C1", "CONJECTURE", "X", "CONJECTURED", 0.6, "island", "smoke")
        assert db.claims()[0]["id"] == "C1"

        ext = project / ".mathlab" / "extensions"
        (ext / "double.py").write_text(
            "import sys,json\nx=json.load(sys.stdin)\nprint(json.dumps({'value': 2*x['value']}))\n",
            encoding="utf-8",
        )
        (ext / "manifest.json").write_text(
            json.dumps({"tools": {"double": {"description": "Double a number", "entrypoint": "double.py"}}}),
            encoding="utf-8",
        )
        result = await ExtensionRegistry(project).run("double", {"value": 21})
        assert result["ok"] and result["result"]["value"] == 42
        print("MathLab dependency-free smoke checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
