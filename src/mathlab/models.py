from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ClaimStatus(StrEnum):
    IDEA = "IDEA"
    CONJECTURED = "CONJECTURED"
    COMPUTATIONALLY_VERIFIED = "COMPUTATIONALLY_VERIFIED"
    PROVISIONAL_PROOF = "PROVISIONAL_PROOF"
    INDEPENDENTLY_VERIFIED = "INDEPENDENTLY_VERIFIED"
    FORMALLY_VERIFIED = "FORMALLY_VERIFIED"
    REFUTED = "REFUTED"
    DISPUTED = "DISPUTED"


class TaskStatus(StrEnum):
    OPEN = "OPEN"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    PAUSED = "PAUSED"


class FeatureStatus(StrEnum):
    OPEN = "OPEN"
    RUNNING = "RUNNING"
    FULFILLED = "FULFILLED"
    REJECTED = "REJECTED"


@dataclass(slots=True)
class AgentSpec:
    id: str
    role: str
    island: str
    task_id: str | None = None
    workspace: str | None = None


@dataclass(slots=True)
class ShellResult:
    stdout: str
    stderr: str
    exit_code: int | None
    timed_out: bool = False

    def as_openai(self) -> dict[str, Any]:
        outcome: dict[str, Any]
        if self.timed_out:
            outcome = {"type": "timeout"}
        else:
            outcome = {"type": "exit", "exit_code": self.exit_code or 0}
        return {"stdout": self.stdout, "stderr": self.stderr, "outcome": outcome}


@dataclass(slots=True)
class Usage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0


@dataclass(slots=True)
class AgentResult:
    text: str
    response_id: str | None
    usage: Usage = field(default_factory=Usage)
    completed: bool = True
