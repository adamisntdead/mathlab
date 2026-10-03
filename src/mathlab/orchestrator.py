from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Awaitable, Callable

from .config import load_config
from .db import Blackboard
from .openai_runner import OpenAIResearchRunner
from .project import new_id

LogFn = Callable[[str, str], Awaitable[None]]


class Orchestrator:
    def __init__(self, project_dir: Path, logger: LogFn | None = None):
        self.project_dir = project_dir
        self.config = load_config(project_dir)
        self.db = Blackboard(project_dir / ".mathlab" / "state.sqlite")
        self.runner = OpenAIResearchRunner(project_dir, self.db)
        self.logger = logger or self._default_logger
        self.stop_event = asyncio.Event()
        self.pause_event = asyncio.Event()
        self.epoch = 0

    async def _default_logger(self, kind: str, text: str) -> None:
        self.db.event(kind, "runtime", {"text": text})

    async def log(self, kind: str, text: str, actor: str = "runtime") -> None:
        self.db.event(kind, actor, {"text": text})
        await self.logger(kind, text)

    def request_stop(self) -> None:
        self.stop_event.set()

    def pause(self) -> None:
        self.pause_event.set()

    def resume(self) -> None:
        self.pause_event.clear()

    async def _wait_if_paused(self) -> None:
        while self.pause_event.is_set() and not self.stop_event.is_set():
            await asyncio.sleep(0.5)

    async def _run_agent(self, role: str, island: str, task_text: str, task_id: str | None = None, agent_id: str | None = None) -> None:
        aid = agent_id or new_id("A")

        async def agent_logger(kind: str, text: str) -> None:
            self.db.event(kind, aid, {"text": text})
            await self.logger(kind, f"[{aid}] {text}")

        try:
            await self.runner.run(aid, role, island, task_text, agent_logger, task_id)
            if task_id:
                self.db.update_task(task_id, "DONE")
        except Exception as exc:  # keep the lab alive when one worker dies
            self.db.upsert_agent(aid, role, island, task_id, "FAILED", str(exc)[:500])
            if task_id:
                self.db.update_task(task_id, "FAILED")
            await agent_logger("agent.error", repr(exc))

    async def seed_if_needed(self) -> None:
        if self.db.count("claims") or self.db.count("tasks"):
            return
        await self.log("orchestrator.seed", "No research state found; starting Cartographer.")
        await self._run_agent(
            "cartographer", "mapping",
            "Read the handoff carefully and build the initial research map. Publish conservative claims and create 6-12 diverse, concrete research tasks."
        )

    async def run_director(self) -> None:
        n = int(self.config["research"].get("tasks_per_epoch", 6))
        await self._run_agent(
            "director", "director",
            f"Plan the next research epoch. Inspect current state and create up to {n} high-value OPEN tasks. Do not solve them yourself. Preserve several genuinely different approaches."
        )

    async def schedule_reviews(self) -> None:
        for claim in self.db.claims_needing_review():
            tid = new_id("T")
            self.db.create_task(
                tid,
                f"Independent verification of {claim['id']}",
                f"Independently verify claim {claim['id']}: {claim['statement']}. Audit any artifact/evidence recorded on the blackboard. Publish a verdict and update status only if justified.",
                "REVIEW", "verification", 0.99, "orchestrator",
            )

    async def handle_feature_requests(self) -> None:
        if not self.config.get("ra", {}).get("enabled", True):
            return
        open_reqs = self.db.feature_requests("OPEN")
        if not open_reqs:
            return
        for req in open_reqs[:2]:
            self.db.resolve_feature(req["id"], "RUNNING", "RA assigned")
            text = (
                f"Capability request {req['id']} from {req['requester']}:\n"
                f"TITLE: {req['title']}\nDESCRIPTION: {req['description']}\n"
                f"ACCEPTANCE TEST: {req['acceptance_test']}\n\n"
                "Implement this as a hot-loadable project extension if feasible. Execute the acceptance test, then call resolve_capability_request."
            )
            await self._run_agent("framework_engineer", "framework", text, agent_id=new_id("RA"))
            latest = {x["id"]: x for x in self.db.feature_requests()}.get(req["id"])
            if latest and latest["status"] == "RUNNING":
                self.db.resolve_feature(req["id"], "OPEN", "RA attempt ended without a tested resolution; queued for retry")

    def _role_for_task(self, task: dict) -> str:
        action = task["action"]
        if action == "REVIEW":
            return "verifier"
        if action == "COMPUTE":
            return "experimentalist"
        if action == "FALSIFY":
            return "falsifier"
        if action == "SYNTHESIZE":
            return "synthesizer"
        return "researcher"

    async def run_open_tasks(self) -> None:
        max_agents = int(self.config["research"]["max_agents"])
        tasks = self.db.open_tasks(limit=max_agents)
        coros = []
        for task in tasks:
            self.db.update_task(task["id"], "RUNNING")
            role = self._role_for_task(task)
            prompt = f"TASK {task['id']} — {task['title']}\n\n{task['description']}\n\nAction: {task['action']}"
            coros.append(self._run_agent(role, task["island"], prompt, task["id"]))
        if coros:
            await asyncio.gather(*coros)

    async def seminar(self) -> None:
        await self._run_agent(
            "synthesizer", "seminar",
            "Run a cross-island seminar. Compare recent findings and failures. Publish any synthesis that is itself mathematically substantive, send targeted messages between islands, and create at most 3 cross-pollination tasks. Do not collapse distinct approaches prematurely."
        )

    async def run(self) -> None:
        await self.seed_if_needed()
        max_epochs = int(self.config["research"].get("max_epochs", 1000))
        budget = float(self.config["research"].get("budget_usd", 200.0))
        seminar_every = int(self.config["research"].get("seminar_every", 4))
        while not self.stop_event.is_set() and self.epoch < max_epochs:
            await self._wait_if_paused()
            if self.stop_event.is_set():
                break
            if self.db.total_cost() >= budget:
                await self.log("orchestrator.budget", f"Budget reached: ${self.db.total_cost():.2f} / ${budget:.2f}")
                break
            self.epoch += 1
            await self.log("orchestrator.epoch", f"Starting epoch {self.epoch}; estimated spend ${self.db.total_cost():.2f}/${budget:.2f}")
            await self.handle_feature_requests()
            await self.schedule_reviews()
            if not self.db.open_tasks():
                await self.run_director()
            await self.run_open_tasks()
            await self.schedule_reviews()
            if seminar_every and self.epoch % seminar_every == 0:
                await self.seminar()
        await self.log("orchestrator.stop", f"Stopped after epoch {self.epoch}; estimated spend ${self.db.total_cost():.2f}")
