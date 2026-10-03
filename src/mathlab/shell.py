from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Awaitable, Callable

from .models import ShellResult

LogFn = Callable[[str, str], Awaitable[None]]


class LocalShellExecutor:
    """Execute model-requested shell commands in the user's local VM workspace.

    Stdout/stderr are streamed to the event logger while also being retained (tail-capped) for the
    shell_call_output returned to the model.
    """

    def __init__(
        self,
        cwd: Path,
        project_dir: Path,
        default_timeout_s: int = 300,
        max_output: int = 32000,
        logger: LogFn | None = None,
    ):
        self.cwd = cwd
        self.project_dir = project_dir
        self.default_timeout_s = default_timeout_s
        self.max_output = max_output
        self.logger = logger

    async def _drain(self, stream: asyncio.StreamReader, kind: str, chunks: list[bytes]) -> None:
        while True:
            block = await stream.readline()
            if not block:
                break
            chunks.append(block)
            # Bound in-memory capture while preserving a useful tail.
            total = sum(len(x) for x in chunks)
            while total > self.max_output * 2 and len(chunks) > 1:
                total -= len(chunks.pop(0))
            if self.logger:
                await self.logger(kind, block.decode(errors="replace"))

    async def run(
        self,
        command: str,
        timeout_ms: int | None = None,
        max_output_length: int | None = None,
    ) -> ShellResult:
        timeout = (timeout_ms / 1000.0) if timeout_ms else float(self.default_timeout_s)
        max_len = int(max_output_length or self.max_output)
        if self.logger:
            await self.logger("shell.command", command)
        env = os.environ.copy()
        env["PATH"] = f"{Path(sys.executable).parent}:{env.get('PATH', '')}"
        env["MATHLAB_PYTHON"] = sys.executable
        env["MATHLAB_PROJECT"] = str(self.project_dir.resolve())
        env["MATHLAB_WORKSPACE"] = str(self.cwd.resolve())
        proc = await asyncio.create_subprocess_exec(
            "/bin/bash",
            "-lc",
            command,
            cwd=str(self.cwd),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdout is not None and proc.stderr is not None
        out_chunks: list[bytes] = []
        err_chunks: list[bytes] = []
        out_task = asyncio.create_task(self._drain(proc.stdout, "shell.stdout", out_chunks))
        err_task = asyncio.create_task(self._drain(proc.stderr, "shell.stderr", err_chunks))
        timed_out = False
        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            timed_out = True
            proc.kill()
            await proc.wait()
        await asyncio.gather(out_task, err_task)

        stdout = b"".join(out_chunks).decode(errors="replace")[-max_len:]
        stderr = b"".join(err_chunks).decode(errors="replace")[-max_len:]
        result = ShellResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=None if timed_out else proc.returncode,
            timed_out=timed_out,
        )
        if self.logger:
            await self.logger(
                "shell.done",
                f"exit={result.exit_code} timeout={result.timed_out} stdout_chars={len(stdout)} stderr_chars={len(stderr)}",
            )
        return result
