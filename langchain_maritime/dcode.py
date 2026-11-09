"""`dcode --sandbox maritime`: the Maritime provider for Deep Agents Code.

Installing `langchain-maritime` registers this provider under the
`deepagents_code.sandbox_providers` entry point, so Deep Agents Code finds it
without any config:

```bash
dcode install langchain-maritime --package
export MARITIME_API_KEY=mk_...
dcode --sandbox maritime
```

This module imports `deepagents_code`, which only Deep Agents Code installs.
Deep Agents itself never loads it.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from deepagents_code.integrations.sandbox_provider import (
    SandboxInstallHint,
    SandboxNotFoundError,
    SandboxProvider,
    SandboxProviderMetadata,
)
from maritime import Maritime, MaritimeSandboxError

from langchain_maritime.sandbox import MaritimeSandbox

if TYPE_CHECKING:
    from deepagents.backends.protocol import SandboxBackendProtocol

WORKING_DIR = "/home/user"
"""The sandbox user's home, where Deep Agents Code starts."""

_CREATE_OPTIONS = frozenset(
    {
        "size",
        "vcpu",
        "memory_mib",
        "disk_gib",
        "env",
        "metadata",
        "name",
        "end_user",
        "idle_timeout_seconds",
        "on_idle",
        "time_limit_seconds",
    }
)
_GONE = frozenset({"resource_not_found", "sandbox_ended", "not_found"})


def _api_key() -> str | None:
    return os.environ.get("DEEPAGENTS_CODE_MARITIME_API_KEY") or os.environ.get("MARITIME_API_KEY")


class MaritimeProvider(SandboxProvider):
    """Creates and ends Maritime sandboxes for Deep Agents Code."""

    def __init__(self, *, client: Maritime | None = None) -> None:
        """Connect to Maritime.

        Args:
            client: A Maritime client. Defaults to one built from
                `MARITIME_API_KEY` (or `DEEPAGENTS_CODE_MARITIME_API_KEY`).

        Raises:
            ValueError: If no API key is set.
        """
        if client is None:
            key = _api_key()
            if not key:
                msg = (
                    "No Maritime API key found. Set MARITIME_API_KEY "
                    "(or DEEPAGENTS_CODE_MARITIME_API_KEY). Create one at maritime.sh/settings/api-keys."
                )
                raise ValueError(msg)
            client = Maritime(api_key=key)
        self._client = client

    @property
    def metadata(self) -> SandboxProviderMetadata:
        """How Deep Agents Code should describe and use this provider."""
        return SandboxProviderMetadata(
            name="maritime",
            working_dir=WORKING_DIR,
            install=SandboxInstallHint(kind="package", name="langchain-maritime"),
            supports_sandbox_id=True,
            supports_snapshot_name=True,
            backend_module="langchain_maritime",
        )

    def get_or_create(
        self,
        *,
        sandbox_id: str | None = None,
        snapshot: str | None = None,
        timeout: int = 30 * 60,
        **kwargs: Any,  # noqa: ANN401  # validated against _CREATE_OPTIONS
    ) -> SandboxBackendProtocol:
        """Connect to a sandbox by id or name, or create a new one.

        Args:
            sandbox_id: An existing sandbox id or name. None creates one.
            snapshot: A saved snapshot or template to start a new sandbox from.
            timeout: Default command timeout in seconds.
            **kwargs: Maritime create options from your Deep Agents Code
                config, such as `size`, `idle_timeout_seconds` or `env`.

        Returns:
            A `MaritimeSandbox` backend.

        Raises:
            TypeError: If an option is not a Maritime create option.
            ValueError: If `snapshot` is combined with `sandbox_id`.
            SandboxNotFoundError: If `sandbox_id` does not exist or has ended.
        """
        unknown = sorted(set(kwargs) - _CREATE_OPTIONS)
        if unknown:
            msg = f"Received unsupported arguments: {unknown}"
            raise TypeError(msg)
        if sandbox_id is not None:
            if snapshot is not None:
                msg = "snapshot only applies when creating a new sandbox"
                raise ValueError(msg)
            try:
                sandbox = self._client.sandboxes.get(sandbox_id)
            except MaritimeSandboxError as exc:
                if exc.code in _GONE:
                    msg = f"Maritime sandbox {sandbox_id!r} was not found"
                    raise SandboxNotFoundError(msg) from exc
                raise
            if sandbox.state == "ended":
                msg = f"Maritime sandbox {sandbox_id!r} has ended"
                raise SandboxNotFoundError(msg)
            return MaritimeSandbox(sandbox=sandbox, timeout=timeout)

        options: dict[str, Any] = {"idle_timeout_seconds": 1800, "on_idle": "pause", **kwargs}
        options.setdefault("metadata", {}).setdefault("created_by", "deepagents-code")
        sandbox = self._client.sandboxes.create(from_=snapshot, **options)
        return MaritimeSandbox(sandbox=sandbox, timeout=timeout)

    def delete(self, *, sandbox_id: str, **kwargs: Any) -> None:  # noqa: ARG002, ANN401  # interface signature
        """End a sandbox. A sandbox that is already gone counts as deleted."""
        try:
            self._client.sandboxes.get(sandbox_id).kill()
        except MaritimeSandboxError as exc:
            if exc.code not in _GONE:
                raise
