from __future__ import annotations

import importlib.metadata
from pathlib import Path

import pytest
from deepagents.backends.protocol import SandboxBackendProtocol
from maritime import MaritimeSandboxError

from langchain_maritime import MaritimeSandbox
from langchain_maritime.sandbox import _map_file_error

from .fakes import FakeCommand, FakeMaritime, FakeSandbox


@pytest.fixture
def sandbox() -> FakeSandbox:
    return FakeSandbox()


@pytest.fixture
def backend(sandbox: FakeSandbox) -> MaritimeSandbox:
    return MaritimeSandbox(sandbox=sandbox)  # type: ignore[arg-type]


def test_is_a_sandbox_backend(backend: MaritimeSandbox, sandbox: FakeSandbox) -> None:
    assert isinstance(backend, SandboxBackendProtocol)
    assert backend.id == sandbox.id
    assert backend.sandbox is sandbox


def test_rejects_negative_timeouts(sandbox: FakeSandbox, backend: MaritimeSandbox) -> None:
    with pytest.raises(ValueError):
        MaritimeSandbox(sandbox=sandbox, timeout=-1)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        backend.execute("true", timeout=-5)


# execute ---------------------------------------------------------------------


def test_execute_runs_bash_and_returns_exit_code(backend: MaritimeSandbox, sandbox: FakeSandbox) -> None:
    result = backend.execute("echo hi; [[ 1 == 1 ]] && exit 3")
    assert result.exit_code == 3
    assert result.output == "hi\n"
    assert sandbox.calls[-1][1] == ["bash", "-lc", "echo hi; [[ 1 == 1 ]] && exit 3"]


def test_execute_puts_stderr_after_stdout(backend: MaritimeSandbox) -> None:
    result = backend.execute("echo out; echo err >&2")
    assert result.output == "out\n\n<stderr>err</stderr>"


def test_execute_uses_default_explicit_and_unbounded_timeouts(sandbox: FakeSandbox) -> None:
    backend = MaritimeSandbox(sandbox=sandbox, timeout=45)  # type: ignore[arg-type]
    backend.execute("true")
    assert sandbox.calls[-1][2] == 45
    backend.execute("true", timeout=7)
    assert sandbox.calls[-1][2] == 7
    backend.execute("true", timeout=0)
    assert sandbox.calls[-1][2] == 86_400


def test_execute_timeout_keeps_partial_output(backend: MaritimeSandbox) -> None:
    result = backend.execute("echo started; sleep 5", timeout=1)
    assert result.exit_code == 124
    assert "Command timed out after 1 seconds" in result.output
    assert result.truncated is False


def test_execute_keeps_large_output_whole(backend: MaritimeSandbox, sandbox: FakeSandbox) -> None:
    sandbox.next_result = FakeCommand(exit_code=0, stdout="x" * 600_000, stderr="")
    result = backend.execute("yes")
    assert result.truncated is False
    assert result.output == "x" * 600_000


def test_execute_passes_maritime_truncation_through(backend: MaritimeSandbox, sandbox: FakeSandbox) -> None:
    sandbox.next_result = FakeCommand(exit_code=0, stdout="short", stderr="", truncated=True)
    assert backend.execute("x").truncated is True


def test_execute_reports_signal_kill_as_137(backend: MaritimeSandbox, sandbox: FakeSandbox) -> None:
    sandbox.next_result = FakeCommand(exit_code=None, stdout="", stderr="")
    assert backend.execute("x").exit_code == 137


def test_execute_raises_other_maritime_errors(backend: MaritimeSandbox, sandbox: FakeSandbox) -> None:
    sandbox.state = "ended"
    with pytest.raises(MaritimeSandboxError, match="sandbox_ended"):
        backend.execute("true")


# files -----------------------------------------------------------------------


def test_upload_then_download_keeps_bytes_and_order(backend: MaritimeSandbox, tmp_path: Path) -> None:
    a, b = str(tmp_path / "deep" / "a.bin"), str(tmp_path / "b.txt")
    up = backend.upload_files([(a, bytes(range(256))), ("relative.txt", b"x"), (b, b"text")])
    assert [(r.path, r.error) for r in up] == [(a, None), ("relative.txt", "invalid_path"), (b, None)]
    down = backend.download_files([b, a])
    assert [(r.path, r.content, r.error) for r in down] == [(b, b"text", None), (a, bytes(range(256)), None)]


def test_download_errors_are_per_file(backend: MaritimeSandbox, tmp_path: Path) -> None:
    (tmp_path / "ok.txt").write_text("ok")
    responses = backend.download_files(
        [str(tmp_path / "missing.txt"), str(tmp_path), "relative.txt", str(tmp_path / "ok.txt")]
    )
    assert [r.error for r in responses] == ["file_not_found", "is_directory", "invalid_path", None]
    assert responses[3].content == b"ok"


def test_upload_over_a_directory_is_is_directory(backend: MaritimeSandbox, tmp_path: Path) -> None:
    (response,) = backend.upload_files([(str(tmp_path), b"x")])
    assert response.error == "is_directory"


def test_errors_unrelated_to_the_file_keep_maritime_message() -> None:
    err = MaritimeSandboxError(402, code="plan_required", message="Upgrade to keep going")
    assert _map_file_error(err) == "plan_required: Upgrade to keep going"
    assert (
        _map_file_error(MaritimeSandboxError(403, code="permission_denied", message="no"))
        == "permission_denied"
    )


# The helpers BaseSandbox builds on execute() ---------------------------------
# grep and glob need GNU tools, so they are covered on real Linux by the live
# standard suite (tests/integration_tests) rather than here.


def test_deep_agents_file_tools_work_end_to_end(backend: MaritimeSandbox, tmp_path: Path) -> None:
    path = str(tmp_path / "src" / "app.py")
    assert backend.write(path, "first").error is None
    assert backend.write(path, "def hello():\n    return 'hi'\n").error is None  # write overwrites

    read = backend.read(path)
    assert read.error is None and "return 'hi'" in str(read.file_data)

    edit = backend.edit(path, "'hi'", "'ahoy'")
    assert edit.error is None
    assert (tmp_path / "src" / "app.py").read_text() == "def hello():\n    return 'ahoy'\n"

    listing = backend.ls(str(tmp_path))
    assert listing.error is None and any(e["path"].rstrip("/").endswith("src") for e in listing.entries)


async def test_async_methods_work(backend: MaritimeSandbox, tmp_path: Path) -> None:
    result = await backend.aexecute("echo async")
    assert result.output == "async\n"
    up = await backend.aupload_files([(str(tmp_path / "a.txt"), b"a")])
    assert up[0].error is None


# create() and kill() ---------------------------------------------------------


def test_create_forwards_options(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeMaritime()
    monkeypatch.setattr("langchain_maritime.sandbox.Maritime", lambda api_key=None: fake)
    backend = MaritimeSandbox.create(timeout=60, size="large", idle_timeout_seconds=600)
    (sandbox,) = fake.sandboxes.created
    assert sandbox.create_kwargs == {"size": "large", "idle_timeout_seconds": 600}
    assert backend.id == sandbox.id
    backend.kill()
    assert sandbox.state == "ended"


def test_package_metadata() -> None:
    import langchain_maritime

    assert langchain_maritime.__version__ == importlib.metadata.version("langchain-maritime")
