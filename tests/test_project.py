from pathlib import Path

from mathlab.project import init_project
from mathlab.config import load_config


def test_init_project(tmp_path: Path):
    handoff = tmp_path / "input.md"
    handoff.write_text("# Target\nProve something.")
    p = init_project(tmp_path / "demo", handoff)
    assert (p / "HANDOFF.md").exists()
    assert (p / "mathlab.toml").exists()
    assert (p / ".mathlab" / "extensions" / "manifest.json").exists()


def test_debug_profile_is_constrained_and_can_be_overridden(tmp_path: Path, monkeypatch):
    project = tmp_path / "demo"
    project.mkdir()
    (project / "mathlab.toml").write_text("[debug]\nenabled = true\n")
    monkeypatch.setenv("MATHLAB_MODEL", "example-model")

    config = load_config(project)

    assert config["model"]["name"] == "example-model"
    assert config["model"]["reasoning"] == "low"
    assert config["research"]["max_agents"] == 1
    assert config["research"]["max_epochs"] == 1
    assert config["execution"]["enable_web_search"] is False
    assert config["ra"]["enabled"] is False
