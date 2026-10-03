from pathlib import Path

import pytest

from mathlab.db import Blackboard
from mathlab.extensions import ExtensionRegistry
from mathlab.tools import ToolRouter, research_tools


async def noop(kind: str, text: str) -> None:
    pass


@pytest.mark.asyncio
async def test_researcher_cannot_self_verify(tmp_path: Path):
    db = Blackboard(tmp_path / "state.sqlite")
    reg = ExtensionRegistry(tmp_path)
    router = ToolRouter(db, reg, "A1", "x", "researcher", noop)
    result = await router.call("publish_finding", {
        "kind": "PROOF",
        "statement": "P",
        "status": "INDEPENDENTLY_VERIFIED",
        "confidence": 1.0,
        "evidence": [],
        "dependencies": [],
        "artifact_path": None,
        "claim_id": None,
    })
    assert result["ok"] is False
    assert db.claims() == []


@pytest.mark.asyncio
async def test_verifier_can_promote_claim(tmp_path: Path):
    db = Blackboard(tmp_path / "state.sqlite")
    db.create_claim("C1", "PROOF", "P", "PROVISIONAL_PROOF", 0.8, "x", "A1")
    router = ToolRouter(db, ExtensionRegistry(tmp_path), "V1", "verification", "verifier", noop)
    result = await router.call("review_claim", {
        "claim_id": "C1", "verdict": "ACCEPT", "reason": "checked", "confidence": 0.95
    })
    assert result["ok"]
    assert db.get_claim("C1")["status"] == "INDEPENDENTLY_VERIFIED"


def test_function_schemas_are_strict_and_extension_args_are_json_strings():
    tools = research_tools()
    assert all(tool["parameters"]["additionalProperties"] is False for tool in tools)
    extension = next(tool for tool in tools if tool["name"] == "run_extension")
    assert extension["parameters"]["properties"]["args"] == {"type": "string"}


@pytest.mark.asyncio
async def test_run_extension_decodes_json_object_arguments(tmp_path: Path):
    registry = ExtensionRegistry(tmp_path)
    script = registry.root / "echo.py"
    script.write_text("import sys\nprint(sys.stdin.read())\n", encoding="utf-8")
    registry.manifest.write_text('{"tools": {"echo": {"entrypoint": "echo.py"}}}', encoding="utf-8")
    router = ToolRouter(Blackboard(tmp_path / "state.sqlite"), registry, "A1", "x", "researcher", noop)

    result = await router.call("run_extension", {"name": "echo", "args": '{"value": 7}'})

    assert result == {"ok": True, "result": {"value": 7}, "stderr": ""}
