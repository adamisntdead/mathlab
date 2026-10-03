from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Awaitable, Callable

from openai import AsyncOpenAI

from .config import load_config
from .cost import estimate_model_cost
from .db import Blackboard
from .extensions import ExtensionRegistry
from .models import AgentResult, Usage
from .prompts import blackboard_digest, build_instructions
from .project import ensure_workspace, read_handoff
from .shell import LocalShellExecutor
from .tools import ToolRouter, research_tools

LogFn = Callable[[str, str], Awaitable[None]]


def _dump(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(exclude_none=True)
    if isinstance(obj, dict):
        return obj
    return dict(obj)


def _usage(response: Any) -> tuple[int, int, int]:
    u = getattr(response, "usage", None)
    if not u:
        return 0, 0, 0
    inp = int(getattr(u, "input_tokens", 0) or 0)
    out = int(getattr(u, "output_tokens", 0) or 0)
    details = getattr(u, "input_tokens_details", None)
    cached = int(getattr(details, "cached_tokens", 0) or 0) if details else 0
    return inp, cached, out




class OpenAIResearchRunner:
    def __init__(self, project_dir: Path, db: Blackboard, client: AsyncOpenAI | None = None):
        self.project_dir = project_dir
        self.db = db
        self.config = load_config(project_dir)
        self.client = client or AsyncOpenAI()
        self.extensions = ExtensionRegistry(project_dir)

    async def run(self, agent_id: str, role: str, island: str, task_text: str, logger: LogFn, task_id: str | None = None) -> AgentResult:
        cfg = self.config
        model = cfg["model"]["name"]
        reasoning = cfg["model"]["reasoning"]
        if role == "director":
            reasoning = cfg["model"].get("director_reasoning", reasoning)
        elif role == "verifier":
            reasoning = cfg["model"].get("verifier_reasoning", reasoning)
        elif role == "framework_engineer":
            reasoning = cfg["model"].get("ra_reasoning", reasoning)

        max_chars = int(cfg["research"].get("max_handoff_chars", 160000))
        handoff = read_handoff(self.project_dir, max_chars)
        digest = blackboard_digest(self.db.claims(), self.db.tasks(60), self.db.feature_requests())
        instructions = build_instructions(role, self.project_dir, handoff, digest, agent_id, island)
        if role == "framework_engineer":
            instructions += "\n\nRA CONFIG\n" + json.dumps(cfg.get("ra", {}), indent=2)
        ws = self.project_dir if role == "framework_engineer" else ensure_workspace(self.project_dir, agent_id)
        shell = LocalShellExecutor(
            ws, self.project_dir,
            default_timeout_s=int(cfg["execution"]["shell_timeout_s"]),
            max_output=int(cfg["execution"]["shell_max_output"]), logger=logger,
        )
        router = ToolRouter(self.db, self.extensions, agent_id, island, role, logger)
        tools: list[dict[str, Any]] = [
            {"type": "shell", "environment": {"type": "local"}},
            *research_tools(include_ra=(role == "framework_engineer"), include_verifier=(role == "verifier")),
        ]
        if cfg["execution"].get("enable_web_search", True):
            tools.append({"type": "web_search"})

        self.db.upsert_agent(agent_id, role, island, task_id, "RUNNING", task_text[:300])
        await logger("agent.start", f"{role} on {task_text[:500]}")
        pending_input: Any = [{"role": "user", "content": task_text}]
        previous_response_id: str | None = None
        total_usage = Usage()
        final_text_parts: list[str] = []
        turn_limit = int(cfg["research"].get("worker_turn_limit", 18))

        for _turn in range(turn_limit):
            kwargs: dict[str, Any] = {
                "model": model,
                "instructions": instructions,
                "input": pending_input,
                "tools": tools,
                "reasoning": {"effort": reasoning},
                "store": True,
                "stream": True,
                "parallel_tool_calls": True,
                "prompt_cache_key": f"mathlab:{self.project_dir.name}:{role}"[:64],
            }
            if previous_response_id:
                kwargs["previous_response_id"] = previous_response_id

            stream = await self.client.responses.create(**kwargs)
            completed_response = None
            streamed_text = ""
            live_buffer = ""
            async for event in stream:
                et = getattr(event, "type", "")
                if et == "response.output_text.delta":
                    delta = getattr(event, "delta", "") or ""
                    streamed_text += delta
                    live_buffer += delta
                    if "\n" in live_buffer or len(live_buffer) >= 400:
                        await logger("model.delta", live_buffer)
                        live_buffer = ""
                elif et == "response.completed":
                    completed_response = getattr(event, "response", None)
                elif et == "response.failed":
                    await logger("agent.error", str(event))
            if live_buffer:
                await logger("model.delta", live_buffer)
            if completed_response is None:
                raise RuntimeError("OpenAI stream ended without response.completed")
            response = completed_response
            previous_response_id = response.id
            if streamed_text:
                final_text_parts.append(streamed_text)

            inp, cached, out = _usage(response)
            cost = estimate_model_cost(model, inp, cached, out)
            total_usage.input_tokens += inp
            total_usage.cached_input_tokens += cached
            total_usage.output_tokens += out
            total_usage.estimated_cost_usd += cost
            self.db.record_usage(agent_id, model, inp, cached, out, cost)

            next_input: list[dict[str, Any]] = []
            tool_calls = 0
            for raw_item in getattr(response, "output", []) or []:
                item = _dump(raw_item)
                typ = item.get("type")
                if typ == "shell_call":
                    tool_calls += 1
                    action = item.get("action", {})
                    commands = action.get("commands", [])
                    results = []
                    for command in commands:
                        r = await shell.run(command, action.get("timeout_ms"), action.get("max_output_length"))
                        results.append(r.as_openai())
                    next_input.append({
                        "type": "shell_call_output",
                        "call_id": item["call_id"],
                        "max_output_length": action.get("max_output_length", cfg["execution"]["shell_max_output"]),
                        "output": results,
                    })
                elif typ == "function_call":
                    tool_calls += 1
                    name = item.get("name", "")
                    try:
                        args = json.loads(item.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    await logger("tool.call", f"{name}({json.dumps(args, ensure_ascii=False)[:1200]})")
                    result = await router.call(name, args)
                    # Opportunistically deliver incoming messages whenever a worker touches the tool loop.
                    unread = self.db.unread_messages(agent_id, island)
                    if unread and name != "check_messages":
                        result["new_messages"] = [
                            {k: m[k] for k in ("id", "sender", "subject", "body", "thread_id")}
                            for m in unread
                        ]
                        self.db.mark_messages_read(agent_id, [m["id"] for m in unread])
                    next_input.append({
                        "type": "function_call_output",
                        "call_id": item["call_id"],
                        "output": json.dumps(result, ensure_ascii=False),
                    })
            if tool_calls == 0:
                self.db.upsert_agent(agent_id, role, island, task_id, "DONE", (streamed_text or "completed")[-500:])
                await logger("agent.done", streamed_text[-1000:] if streamed_text else "completed")
                return AgentResult("".join(final_text_parts), previous_response_id, total_usage, True)
            pending_input = next_input

        self.db.upsert_agent(agent_id, role, island, task_id, "DONE", "turn limit reached")
        await logger("agent.done", "Worker turn limit reached; durable tool-published results were retained.")
        return AgentResult("".join(final_text_parts), previous_response_id, total_usage, False)
