from pathlib import Path

import pytest

from mathlab.shell import LocalShellExecutor


@pytest.mark.asyncio
async def test_shell_streams_and_captures(tmp_path: Path):
    events: list[tuple[str, str]] = []

    async def log(kind: str, text: str) -> None:
        events.append((kind, text))

    ex = LocalShellExecutor(tmp_path, tmp_path, default_timeout_s=3, logger=log)
    result = await ex.run("printf 'one\\ntwo\\n'; printf 'err\\n' >&2")
    assert result.exit_code == 0
    assert "one" in result.stdout and "two" in result.stdout
    assert "err" in result.stderr
    assert any(k == "shell.stdout" and "one" in t for k, t in events)
    assert any(k == "shell.stderr" and "err" in t for k, t in events)
