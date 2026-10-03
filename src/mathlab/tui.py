from __future__ import annotations

import asyncio
import json
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, RichLog, Static

from .config import load_config
from .db import Blackboard
from .orchestrator import Orchestrator
from .project import new_id


class MathLabTUI(App):
    CSS = """
    Screen { layout: vertical; }
    #body { height: 1fr; }
    #left { width: 30%; border: round $primary; }
    #center { width: 45%; border: round $secondary; }
    #right { width: 25%; border: round $accent; }
    .pane-title { text-style: bold; padding: 0 1; }
    #agents, #frontier, #features { height: 1fr; overflow-y: auto; padding: 0 1; }
    #log { height: 1fr; }
    #command { dock: bottom; }
    """

    BINDINGS = [
        ("ctrl+c", "quit_lab", "Stop"),
        ("ctrl+p", "toggle_pause", "Pause/resume"),
        ("ctrl+l", "clear_log", "Clear log"),
    ]

    def __init__(self, project_dir: Path):
        super().__init__()
        self.project_dir = project_dir
        self.config = load_config(project_dir)
        self.db = Blackboard(project_dir / ".mathlab" / "state.sqlite")
        self.orchestrator = Orchestrator(project_dir, self.runtime_log)
        self.last_event_id = 0
        self.runner_task: asyncio.Task | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield Static("AGENTS", classes="pane-title")
                yield Static(id="agents")
                yield Static("CAPABILITY REQUESTS", classes="pane-title")
                yield Static(id="features")
            with Vertical(id="center"):
                yield Static("LIVE RESEARCH LOG", classes="pane-title")
                yield RichLog(id="log", wrap=True, highlight=True, markup=True)
            with Vertical(id="right"):
                yield Static("FRONTIER", classes="pane-title")
                yield Static(id="frontier")
        yield Input(placeholder=":msg TARGET text | :spawn N prompt | :focus CLAIM | :pause | :resume | :stop", id="command")
        yield Footer()

    async def on_mount(self) -> None:
        self.title = f"MathLab — {self.project_dir.name}"
        self.runner_task = asyncio.create_task(self.orchestrator.run())
        hz = max(0.2, float(self.config.get("ui", {}).get("refresh_hz", 2.0)))
        self.set_interval(1.0 / hz, self.refresh_state)

    async def runtime_log(self, kind: str, text: str) -> None:
        log = self.query_one("#log", RichLog)
        if kind in {"shell.stdout", "shell.stderr"} and not self.config.get("ui", {}).get("show_shell_output", True):
            return
        if kind == "model.delta":
            # Deltas are numerous; still show them immediately for the live-research feel.
            log.write(text, scroll_end=True)
        else:
            log.write(f"[dim]{kind}[/dim] {text}", scroll_end=True)

    async def refresh_state(self) -> None:
        agents = self.db.agents()
        atext = []
        for a in agents[:20]:
            icon = {"RUNNING": "●", "DONE": "✓", "FAILED": "×"}.get(a["status"], "○")
            atext.append(f"{icon} {a['id']}  {a['role']}\n   {a['island']}  {a['status']}\n   {(a['last_note'] or '')[:100]}")
        self.query_one("#agents", Static).update("\n\n".join(atext) or "No agents yet")

        claims = self.db.claims(30)
        ctext = []
        for c in claims:
            ctext.append(f"{c['id']}  {c['status']}  {c['confidence']:.2f}\n{c['statement'][:180]}")
        spend = self.db.total_cost()
        self.query_one("#frontier", Static).update(f"Estimated API spend: ${spend:.2f}\n\n" + ("\n\n".join(ctext) or "No claims yet"))

        feats = self.db.feature_requests()
        ftext = [f"{f['id']} {f['status']}\n{f['title'][:90]}" for f in feats[:10]]
        self.query_one("#features", Static).update("\n\n".join(ftext) or "None")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        cmd = event.value.strip()
        event.input.value = ""
        if not cmd:
            return
        log = self.query_one("#log", RichLog)
        try:
            if cmd == ":pause":
                self.orchestrator.pause(); log.write("[yellow]Paused after current calls.[/yellow]")
            elif cmd == ":resume":
                self.orchestrator.resume(); log.write("[green]Resumed.[/green]")
            elif cmd in {":stop", ":quit"}:
                self.orchestrator.request_stop(); log.write("[yellow]Stop requested.[/yellow]")
            elif cmd.startswith(":msg "):
                _, target, body = cmd.split(" ", 2)
                self.db.send_message(new_id("M"), "human", target, "Human intervention", body)
                log.write(f"[cyan]Message sent to {target}[/cyan]")
            elif cmd.startswith(":focus "):
                cid = cmd.split(maxsplit=1)[1]
                self.db.create_task(new_id("T"), f"Human focus: {cid}", f"Prioritize claim/question {cid}. Re-read its evidence and make concrete progress.", "EXPLORE", "human-focus", 1.0, "human")
                log.write(f"[cyan]Focus task created for {cid}[/cyan]")
            elif cmd.startswith(":spawn "):
                _, n_s, prompt = cmd.split(" ", 2)
                n = min(20, max(1, int(n_s)))
                for i in range(n):
                    self.db.create_task(new_id("T"), f"Human-spawned attempt {i+1}/{n}", prompt, "EXPLORE", f"human-{i+1}", 1.0, "human")
                log.write(f"[cyan]Spawned {n} independent tasks.[/cyan]")
            else:
                self.db.send_message(new_id("M"), "human", "all", "Human note", cmd)
                log.write("[cyan]Broadcast human note.[/cyan]")
        except Exception as exc:
            log.write(f"[red]Command error: {exc!r}[/red]")

    async def action_toggle_pause(self) -> None:
        if self.orchestrator.pause_event.is_set():
            self.orchestrator.resume()
        else:
            self.orchestrator.pause()

    async def action_clear_log(self) -> None:
        self.query_one("#log", RichLog).clear()

    async def action_quit_lab(self) -> None:
        self.orchestrator.request_stop()
        self.exit()
