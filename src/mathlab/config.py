from __future__ import annotations

import copy
import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "model": {
        "name": "gpt-6-astra",
        "reasoning": "max",
        "director_reasoning": "high",
        "verifier_reasoning": "max",
        "ra_reasoning": "high",
    },
    "research": {
        "max_agents": 6,
        "budget_usd": 200.0,
        "max_epochs": 1000,
        "tasks_per_epoch": 6,
        "seminar_every": 4,
        "worker_turn_limit": 18,
        "max_handoff_chars": 160000,
    },
    "execution": {
        "shell_timeout_s": 300,
        "shell_max_output": 32000,
        "enable_web_search": True,
    },
    "ra": {
        "enabled": True,
        "allow_pip_install": True,
        "allow_core_patch": False,
    },
    "ui": {
        "refresh_hz": 2.0,
        "show_shell_output": True,
    },
    "debug": {
        "enabled": False,
        "model": "gpt-5.4-mini",
        "reasoning": "low",
        "max_agents": 1,
        "budget_usd": 2.0,
        "max_epochs": 1,
        "tasks_per_epoch": 1,
        "worker_turn_limit": 3,
        "enable_web_search": False,
        "ra_enabled": False,
    },
}


def _merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def load_config(project_dir: Path) -> dict[str, Any]:
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    path = project_dir / "mathlab.toml"
    if path.exists():
        with path.open("rb") as f:
            _merge(cfg, tomllib.load(f))
    if _truthy(os.environ.get("MATHLAB_DEBUG")) or cfg["debug"].get("enabled", False):
        debug = cfg["debug"]
        _merge(cfg, {
            "model": {
                "name": debug["model"],
                "reasoning": debug["reasoning"],
                "director_reasoning": debug["reasoning"],
                "verifier_reasoning": debug["reasoning"],
                "ra_reasoning": debug["reasoning"],
            },
            "research": {key: debug[key] for key in ("max_agents", "budget_usd", "max_epochs", "tasks_per_epoch", "worker_turn_limit")},
            "execution": {"enable_web_search": debug["enable_web_search"]},
            "ra": {"enabled": debug["ra_enabled"]},
        })
    if model := os.environ.get("MATHLAB_MODEL"):
        cfg["model"]["name"] = model
    return cfg


def _truthy(value: str | None) -> bool:
    return value is not None and value.lower() in {"1", "true", "yes", "on"}


EXAMPLE_CONFIG = '''# MathLab project configuration\n\n[model]\nname = "gpt-6-astra"\nreasoning = "max"\ndirector_reasoning = "high"\nverifier_reasoning = "max"\nra_reasoning = "high"\n\n[debug]\n# Enable permanently for this project, or run `mathlab go --debug`.\nenabled = false\nmodel = "gpt-5.4-mini"\nreasoning = "low"\nmax_agents = 1\nbudget_usd = 2.0\nmax_epochs = 1\ntasks_per_epoch = 1\nworker_turn_limit = 3\nenable_web_search = false\nra_enabled = false\n\n[research]\nmax_agents = 6\nbudget_usd = 200.0\nmax_epochs = 1000\ntasks_per_epoch = 6\nseminar_every = 4\nworker_turn_limit = 18\nmax_handoff_chars = 160000\n\n[execution]\nshell_timeout_s = 300\nshell_max_output = 32000\nenable_web_search = true\n\n[ra]\nenabled = true\nallow_pip_install = true\nallow_core_patch = false\n\n[ui]\nrefresh_hz = 2.0\nshow_shell_output = true\n'''
