"""A stand-in for the Maritime SDK that runs commands and files on this machine.

Only the network calls to Maritime are replaced: commands really run under
bash and files really land on disk, so the Deep Agents helpers that
`BaseSandbox` builds on `execute()` (ls, read, grep, glob, edit) run for real.
"""

from __future__ import annotations

import itertools
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maritime import MaritimeSandboxError

_ids = itertools.count(1)


@dataclass
class FakeCommand:
    exit_code: int | None
    stdout: str
    stderr: str
    truncated: bool = False


class FakeFiles:
    def __init__(self, sandbox: FakeSandbox) -> None:
        self._sandbox = sandbox

    def read(self, path: str) -> bytes:
        self._sandbox.calls.append(("files.read", path))
        self._sandbox.check_alive()
        if not path.startswith("/"):
            raise MaritimeSandboxError(400, code="invalid_request", message="path must be an absolute path")
        p = Path(path)
        if p.is_dir():
            raise MaritimeSandboxError(400, code="invalid_request", message=f"{path} is a directory")
        if not p.exists():
            raise MaritimeSandboxError(404, code="file_not_found", message=f"no file at {path}")
        return p.read_bytes()

    def write(self, path: str, data: str | bytes) -> None:
        self._sandbox.calls.append(("files.write", path))
        self._sandbox.check_alive()
        p = Path(path)
        if p.is_dir():
            raise MaritimeSandboxError(400, code="invalid_request", message=f"path is a directory: {path}")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data.encode() if isinstance(data, str) else data)


@dataclass
class FakeSandbox:
    create_kwargs: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"sbx-fake{next(_ids)}")
    state: str = "running"
    calls: list[tuple[Any, ...]] = field(default_factory=list)
    next_result: FakeCommand | None = None

    def __post_init__(self) -> None:
        self.files = FakeFiles(self)

    def check_alive(self) -> None:
        if self.state == "ended":
            raise MaritimeSandboxError(410, code="sandbox_ended", message="the sandbox has ended")

    def run(self, cmd: str | list[str], *, timeout_seconds: int | None = None, **_: Any) -> FakeCommand:
        self.calls.append(("run", cmd, timeout_seconds))
        self.check_alive()
        if self.next_result is not None:
            result, self.next_result = self.next_result, None
            return result
        try:
            done = subprocess.run(
                cmd,
                shell=isinstance(cmd, str),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=os.environ.copy(),
            )
        except subprocess.TimeoutExpired as e:
            partial = FakeCommand(
                exit_code=None,
                stdout=(e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or ""),
                stderr="",
            )
            err = MaritimeSandboxError(408, code="command_timeout", message="timed out", command=partial)  # type: ignore[arg-type]
            raise err from e
        return FakeCommand(exit_code=done.returncode, stdout=done.stdout, stderr=done.stderr)

    def kill(self) -> None:
        self.calls.append(("kill",))
        self.state = "ended"


class FakeSandboxes:
    def __init__(self) -> None:
        self.created: list[FakeSandbox] = []
        self.by_id: dict[str, FakeSandbox] = {}

    def create(self, **kwargs: Any) -> FakeSandbox:
        sandbox = FakeSandbox(create_kwargs=kwargs)
        self.created.append(sandbox)
        self.by_id[sandbox.id] = sandbox
        return sandbox

    def get(self, id_or_name: str) -> FakeSandbox:
        if id_or_name not in self.by_id:
            raise MaritimeSandboxError(404, code="resource_not_found", message="no such sandbox")
        return self.by_id[id_or_name]


class FakeMaritime:
    def __init__(self) -> None:
        self.sandboxes = FakeSandboxes()
