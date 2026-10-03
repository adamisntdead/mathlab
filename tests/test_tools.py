from pathlib import Path

import pytest

from mathlab.db import Blackboard
from mathlab.extensions import ExtensionRegistry
from mathlab.tools import ToolRouter


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
