from pathlib import Path

from mathlab.project import init_project


def test_init_project(tmp_path: Path):
    handoff = tmp_path / "input.md"
    handoff.write_text("# Target\nProve something.")
    p = init_project(tmp_path / "demo", handoff)
    assert (p / "HANDOFF.md").exists()
    assert (p / "mathlab.toml").exists()
    assert (p / ".mathlab" / "extensions" / "manifest.json").exists()
