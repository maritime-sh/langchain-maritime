"""Maritime sandbox backend for Deep Agents."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from deepagents.backends.protocol import (
    FILE_NOT_FOUND,
    INVALID_PATH,
    IS_DIRECTORY,
    PERMISSION_DENIED,
    ExecuteResponse,
    FileDownloadResponse,
    FileOperationError,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox
from maritime import Maritime, MaritimeSandboxError

if TYPE_CHECKING:
    from maritime import Sandbox

logger = logging.getLogger(__name__)

UNBOUNDED_TIMEOUT_SECONDS = 86_400
"""What a timeout of 0 ("wait as long as it takes") becomes: Maritime's longest command."""

TIMEOUT_EXIT_CODE = 124
"""The exit code `timeout(1)` uses, returned when a command runs out of time."""


class MaritimeSandbox(BaseSandbox):
    """A Deep Agents backend that runs commands and files in a Maritime sandbox.

    Every Deep Agents tool (`ls`, `read_file`, `write_file`, `edit_file`,
    `glob`, `grep` and `execute`) runs inside the sandbox, a Linux microVM
    with its own filesystem, network and processes.

    Wrap a sandbox you created with the Maritime SDK:

    ```python
    from maritime import Maritime
    from langchain_maritime import MaritimeSandbox

    sandbox = Maritime().sandboxes.create(idle_timeout_seconds=600)
    backend = MaritimeSandbox(sandbox=sandbox)
    ```

    or let the backend create one with `MaritimeSandbox.create()`.
    """

    def __init__(self, *, sandbox: Sandbox, timeout: int = 30 * 60) -> None:
        """Wrap an existing Maritime sandbox.

        Args:
            sandbox: A `maritime.Sandbox` from `Maritime().sandboxes.create()`
                or `.get()`.
            timeout: Default command timeout in seconds, used when `execute()`
                gets none. 0 waits as long as Maritime allows (24 hours).

        Raises:
            ValueError: If `timeout` is negative.
        """
        if timeout < 0:
            msg = f"timeout must be non-negative, got {timeout}"
            raise ValueError(msg)
        self._sandbox = sandbox
        self._default_timeout = timeout

    @classmethod
    def create(
        cls,
        *,
        api_key: str | None = None,
        timeout: int = 30 * 60,
        **create_kwargs: Any,  # noqa: ANN401  # forwarded to the Maritime SDK unchanged
    ) -> MaritimeSandbox:
        """Create a new Maritime sandbox and wrap it.

        Args:
            api_key: Maritime API key. Defaults to `MARITIME_API_KEY`.
            timeout: Default command timeout in seconds.
            **create_kwargs: Passed to `Maritime().sandboxes.create()`, for
                example `size="large"`, `from_="my-snapshot"`,
                `idle_timeout_seconds=600` or `env={...}`.

        Returns:
            A backend for the new sandbox. Call `kill()` when you are done.
        """
        sandbox = Maritime(api_key=api_key).sandboxes.create(**create_kwargs)
        return cls(sandbox=sandbox, timeout=timeout)

    @property
    def id(self) -> str:
        """The Maritime sandbox id."""
        return self._sandbox.id

    @property
    def sandbox(self) -> Sandbox:
        """The underlying `maritime.Sandbox`, for anything this backend does not wrap."""
        return self._sandbox

    def kill(self) -> None:
        """End the sandbox. Safe to call more than once."""
        self._sandbox.kill()

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        """Run a shell command in the sandbox.

        Args:
            command: A bash command line.
            timeout: Seconds to wait. None uses the backend default, and 0
                waits as long as Maritime allows.

        Returns:
            The combined output, the exit code, and whether the output was cut.
        """
        effective = timeout if timeout is not None else self._default_timeout
        if effective < 0:
            msg = f"timeout must be non-negative, got {effective}"
            raise ValueError(msg)
        seconds = effective or UNBOUNDED_TIMEOUT_SECONDS
        try:
            result = self._sandbox.run(["bash", "-lc", command], timeout_seconds=seconds)
        except MaritimeSandboxError as exc:
            if exc.code != "command_timeout":
                raise
            partial = exc.command
            output = _combine(partial.stdout, partial.stderr) if partial else ""
            note = f"Command timed out after {seconds} seconds"
            output = f"{output}\n{note}" if output else note
            return ExecuteResponse(output=output, exit_code=TIMEOUT_EXIT_CODE, truncated=False)

        # Output is passed through whole: Deep Agents' file helpers return JSON
        # through execute(), and Deep Agents already moves large tool results
        # out of the model's context. Maritime marks output it had to cut.
        output = _combine(result.stdout, result.stderr)
        truncated = bool(result.truncated)
        # A process ended by a signal has no exit code; report it the way a shell does.
        exit_code = result.exit_code if result.exit_code is not None else 137
        return ExecuteResponse(output=output, exit_code=exit_code, truncated=truncated)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Read files from the sandbox. Each path gets its own result, in order."""
        responses: list[FileDownloadResponse] = []
        for path in paths:
            if not path.startswith("/"):
                responses.append(FileDownloadResponse(path=path, content=None, error=INVALID_PATH))
                continue
            try:
                content = self._sandbox.files.read(path)
            except MaritimeSandboxError as exc:
                responses.append(FileDownloadResponse(path=path, content=None, error=_map_file_error(exc)))
                continue
            responses.append(FileDownloadResponse(path=path, content=content, error=None))
        return responses

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Write files into the sandbox, creating parent directories. Results keep the input order."""
        responses: list[FileUploadResponse] = []
        for path, content in files:
            if not path.startswith("/"):
                responses.append(FileUploadResponse(path=path, error=INVALID_PATH))
                continue
            try:
                self._sandbox.files.write(path, content)
            except MaritimeSandboxError as exc:
                responses.append(FileUploadResponse(path=path, error=_map_file_error(exc)))
                continue
            responses.append(FileUploadResponse(path=path, error=None))
        return responses


def _combine(stdout: str | None, stderr: str | None) -> str:
    output = stdout or ""
    err = (stderr or "").strip()
    if err:
        output += f"\n<stderr>{err}</stderr>"
    return output


def _map_file_error(exc: MaritimeSandboxError) -> FileOperationError | str:
    """Map a Maritime file error to a Deep Agents error code.

    Errors that are not about the file itself, such as auth, billing or a
    sandbox that has ended, keep Maritime's own message so the agent sees what
    really went wrong instead of a misleading "file not found".
    """
    message = (exc.message or "").lower()
    if exc.code in {"file_not_found", "resource_not_found"}:
        return FILE_NOT_FOUND
    if exc.code == "permission_denied" or "permission denied" in message:
        return PERMISSION_DENIED
    if "is a directory" in message:
        return IS_DIRECTORY
    if "absolute path" in message or "invalid path" in message:
        return INVALID_PATH
    return str(exc)
