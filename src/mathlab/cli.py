from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .db import Blackboard
from .orchestrator import Orchestrator
from .project import init_project
from .tui import MathLabTUI

app = typer.Typer(no_args_is_help=True, help="MathLab — autonomous, persistent mathematics research.")
console = Console()


@app.command()
def init(name: str, handoff: Path = typer.Argument(..., exists=True, readable=True), directory: Path = typer.Option(Path("."), "--dir")) -> None:
    """Create a new MathLab project from a handoff/research document."""
    destination = (directory / name).resolve()
    init_project(destination, handoff.resolve())
    console.print(f"[green]Created[/green] {destination}")
    console.print("Next: cd into it, export OPENAI_API_KEY=..., then run [bold]mathlab go[/bold].")


@app.command()
def go(
    project: Path = typer.Argument(Path(".")),
    headless: bool = typer.Option(False, "--headless"),
    model: str | None = typer.Option(None, "--model", help="Use this model for this run without editing mathlab.toml."),
    debug: bool = typer.Option(False, "--debug", help="Use the constrained low-cost debug profile."),
) -> None:
    """Start/resume autonomous research, with the TUI by default."""
    project = project.resolve()
    if not (project / "HANDOFF.md").exists():
        raise typer.BadParameter(f"{project} is not a MathLab project (HANDOFF.md missing)")
    if not os.environ.get("OPENAI_API_KEY"):
        console.print("[red]OPENAI_API_KEY is not set.[/red]")
        raise typer.Exit(2)
    if debug:
        os.environ["MATHLAB_DEBUG"] = "1"
    if model:
        os.environ["MATHLAB_MODEL"] = model
    if headless:
        orch = Orchestrator(project, _headless_log)
        asyncio.run(orch.run())
    else:
        MathLabTUI(project).run()


async def _headless_log(kind: str, text: str) -> None:
    if kind != "model.delta":
        console.print(f"[dim]{kind}[/dim] {text}")
    else:
        console.print(text, end="")


@app.command()
def status(project: Path = typer.Argument(Path("."))) -> None:
    """Show durable project status without starting agents."""
    project = project.resolve()
    db = Blackboard(project / ".mathlab" / "state.sqlite")
    console.print(f"[bold]{project.name}[/bold] — estimated spend ${db.total_cost():.2f}")
    table = Table("ID", "Status", "Confidence", "Island", "Statement")
    for c in db.claims(20):
        table.add_row(c["id"], c["status"], f"{c['confidence']:.2f}", c["island"], c["statement"][:100])
    console.print(table)
    console.print(f"Open tasks: {len(db.open_tasks())}; capability requests: {len(db.feature_requests('OPEN'))}")


@app.command()
def doctor() -> None:
    """Check local research environment."""
    table = Table("Capability", "Found", "Path / note")
    for binary in ["python", "sage", "gp", "lean", "lake", "git", "pdflatex", "rg"]:
        path = shutil.which(binary)
        table.add_row(binary, "yes" if path else "no", path or "optional")
    table.add_row("OPENAI_API_KEY", "yes" if os.environ.get("OPENAI_API_KEY") else "no", "environment variable")
    console.print(table)
    console.print("Only Python + API key are required. Sage/PARI/Lean/LaTeX are optional but useful.")


if __name__ == "__main__":
    app()
