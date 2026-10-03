from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from .db import Blackboard
from .extensions import ExtensionRegistry
from .project import new_id

LogFn = Callable[[str, str], Awaitable[None]]


def function_tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required, "additionalProperties": False},
        "strict": True,
    }


def research_tools(include_ra: bool = False, include_verifier: bool = False) -> list[dict[str, Any]]:
    tools = [
        function_tool("log_progress", "Write a concise substantive progress note visible in the live TUI.", {"note": {"type": "string"}}, ["note"]),
        function_tool("publish_finding", "Publish or update a durable mathematical finding on the blackboard.", {
            "kind": {"type": "string", "enum": ["CLAIM", "CONJECTURE", "QUESTION", "COUNTEREXAMPLE", "COMPUTATION", "PROOF", "OBSTRUCTION", "LITERATURE_RESULT", "DEAD_END"]},
            "statement": {"type": "string"},
            "status": {"type": "string", "enum": ["IDEA", "CONJECTURED", "COMPUTATIONALLY_VERIFIED", "PROVISIONAL_PROOF", "INDEPENDENTLY_VERIFIED", "FORMALLY_VERIFIED", "REFUTED", "DISPUTED"]},
            "confidence": {"type": "number"},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "dependencies": {"type": "array", "items": {"type": "string"}},
            "artifact_path": {"type": ["string", "null"]},
            "claim_id": {"type": ["string", "null"]},
        }, ["kind", "statement", "status", "confidence", "evidence", "dependencies", "artifact_path", "claim_id"]),
        function_tool("create_task", "Create a follow-up research task for this or another island.", {
            "title": {"type": "string"}, "description": {"type": "string"},
            "action": {"type": "string", "enum": ["EXPLORE", "PROVE", "FALSIFY", "COMPUTE", "LITERATURE", "GENERALIZE", "REFORMULATE", "REVIEW", "SYNTHESIZE"]},
            "island": {"type": "string"}, "priority": {"type": "number"},
        }, ["title", "description", "action", "island", "priority"]),
        function_tool("send_message", "Send a concrete question/result to an agent, island, or all agents.", {
            "target": {"type": "string", "description": "agent id, island:<name>, or all"},
            "subject": {"type": "string"}, "body": {"type": "string"}, "thread_id": {"type": ["string", "null"]},
        }, ["target", "subject", "body", "thread_id"]),
        function_tool("check_messages", "Read unread messages sent to you or your island.", {}, []),
        function_tool("get_claim", "Retrieve the full durable record for one claim, including evidence, dependencies, and artifact path.", {"claim_id": {"type": "string"}}, ["claim_id"]),
        function_tool("search_claims", "Search durable claims by text/kind.", {"query": {"type": "string"}, "limit": {"type": "integer"}}, ["query", "limit"]),
        function_tool("list_tasks", "Inspect recent task history including completed and failed attempts.", {"limit": {"type": "integer"}}, ["limit"]),
        function_tool("request_peer_review", "Create an independent review task for a claim.", {
            "claim_id": {"type": "string"}, "focus": {"type": "string"}
        }, ["claim_id", "focus"]),
        function_tool("request_capability", "Ask the RA framework engineer to hot-add a missing research capability.", {
            "title": {"type": "string"}, "description": {"type": "string"}, "acceptance_test": {"type": "string"}
        }, ["title", "description", "acceptance_test"]),
        function_tool("list_capabilities", "List project-local hot-added RA extension tools.", {}, []),
        function_tool("run_extension", "Run a named hot-added project extension. Pass its JSON object arguments as a JSON-encoded string in args.", {
            "name": {"type": "string"}, "args": {"type": "string"}
        }, ["name", "args"]),
    ]
    if include_verifier:
        tools.append(function_tool("review_claim", "Record an independent referee verdict on an existing claim. This is the only tool that can promote a claim to independently verified.", {
            "claim_id": {"type": "string"},
            "verdict": {"type": "string", "enum": ["ACCEPT", "FIXABLE", "REJECT", "UNCERTAIN"]},
            "reason": {"type": "string"},
            "confidence": {"type": "number"}
        }, ["claim_id", "verdict", "reason", "confidence"]))
    if include_ra:
        tools.append(function_tool("resolve_capability_request", "Mark a capability request fulfilled/rejected after testing it.", {
            "request_id": {"type": "string"},
            "status": {"type": "string", "enum": ["FULFILLED", "REJECTED"]},
            "resolution": {"type": "string"},
        }, ["request_id", "status", "resolution"]))
    return tools


class ToolRouter:
    def __init__(self, db: Blackboard, extensions: ExtensionRegistry, agent_id: str, island: str, role: str, logger: LogFn):
        self.db = db
        self.extensions = extensions
        self.agent_id = agent_id
        self.island = island
        self.role = role
        self.logger = logger

    async def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "log_progress":
            note = args["note"]
            self.db.update_agent_note(self.agent_id, note, "RUNNING")
            self.db.event("agent.note", self.agent_id, {"note": note})
            await self.logger("agent.note", note)
            return {"ok": True}
        if name == "publish_finding":
            requested_status = args["status"]
            if requested_status in {"INDEPENDENTLY_VERIFIED", "FORMALLY_VERIFIED"}:
                return {"ok": False, "error": "Researchers cannot self-promote to independent/formal verification. Use the verifier/formal-check workflow."}
            cid = args.get("claim_id") or new_id("C")
            existing = self.db.get_claim(cid)
            if existing and existing.get("created_by") != self.agent_id:
                return {"ok": False, "error": "Cannot overwrite another agent's claim; publish a new finding or request review."}
            self.db.create_claim(cid, args["kind"], args["statement"], requested_status, float(args["confidence"]), self.island, self.agent_id, args.get("evidence"), args.get("dependencies"), args.get("artifact_path"))
            return {"ok": True, "claim_id": cid}
        if name == "create_task":
            tid = new_id("T")
            self.db.create_task(tid, args["title"], args["description"], args["action"], args["island"], float(args["priority"]), self.agent_id)
            return {"ok": True, "task_id": tid}
        if name == "send_message":
            mid = new_id("M")
            self.db.send_message(mid, self.agent_id, args["target"], args["subject"], args["body"], args.get("thread_id"))
            return {"ok": True, "message_id": mid}
        if name == "check_messages":
            msgs = self.db.unread_messages(self.agent_id, self.island)
            self.db.mark_messages_read(self.agent_id, [m["id"] for m in msgs])
            return {"messages": [{k: m[k] for k in ("id", "sender", "subject", "body", "thread_id", "created_at")} for m in msgs]}
        if name == "get_claim":
            claim = self.db.get_claim(args["claim_id"])
            return {"claim": claim}
        if name == "search_claims":
            limit = max(1, min(100, int(args["limit"])))
            return {"claims": self.db.search_claims(args["query"], limit)}
        if name == "list_tasks":
            limit = max(1, min(100, int(args["limit"])))
            return {"tasks": self.db.tasks(limit)}
        if name == "request_peer_review":
            tid = new_id("T")
            self.db.create_task(tid, f"Independent review of {args['claim_id']}", f"Review claim {args['claim_id']}. Focus: {args['focus']}", "REVIEW", "verification", 0.95, self.agent_id)
            return {"ok": True, "task_id": tid}
        if name == "request_capability":
            rid = new_id("F")
            self.db.create_feature_request(rid, self.agent_id, args["title"], args["description"], args["acceptance_test"])
            return {"ok": True, "request_id": rid, "message": "RA will see this request on the next scheduling pass."}
        if name == "list_capabilities":
            return {"tools": self.extensions.tools()}
        if name == "run_extension":
            try:
                extension_args = json.loads(args["args"])
            except json.JSONDecodeError:
                return {"ok": False, "error": "Extension args must be a valid JSON object string."}
            if not isinstance(extension_args, dict):
                return {"ok": False, "error": "Extension args must decode to a JSON object."}
            return await self.extensions.run(args["name"], extension_args)
        if name == "review_claim":
            if self.role != "verifier":
                return {"ok": False, "error": "Only verifier agents can record independent review verdicts."}
            claim = self.db.get_claim(args["claim_id"])
            if not claim:
                return {"ok": False, "error": "Unknown claim"}
            verdict = args["verdict"]
            if verdict == "ACCEPT":
                status = "INDEPENDENTLY_VERIFIED"
            elif verdict == "FIXABLE":
                status = "PROVISIONAL_PROOF"
            else:
                status = "DISPUTED"
            self.db.update_claim_status(args["claim_id"], status, float(args["confidence"]))
            self.db.event("claim.review", self.agent_id, {"claim_id": args["claim_id"], "verdict": verdict, "reason": args["reason"], "confidence": args["confidence"]})
            return {"ok": True, "claim_id": args["claim_id"], "new_status": status}
        if name == "resolve_capability_request":
            self.db.resolve_feature(args["request_id"], args["status"], args["resolution"])
            return {"ok": True}
        return {"ok": False, "error": f"Unknown function tool: {name}"}
