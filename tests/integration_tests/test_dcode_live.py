"""The Deep Agents Code provider against a real Maritime account. Run with: pytest -m live."""

from __future__ import annotations

import os
import uuid

import pytest

pytest.importorskip("deepagents_code", reason="Deep Agents Code is not installed (it needs Python 3.14)")
from deepagents_code.integrations.sandbox_provider import SandboxNotFoundError
from maritime import Maritime

from langchain_maritime.dcode import MaritimeProvider

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("MARITIME_API_KEY"), reason="needs MARITIME_API_KEY"),
]


def test_create_reconnect_and_delete() -> None:
    provider = MaritimeProvider()
    backend = provider.get_or_create(idle_timeout_seconds=300, on_idle="kill", metadata={"test": "dcode"})
    try:
        assert backend.execute("echo hello > /home/user/note.txt").exit_code == 0
        again = provider.get_or_create(sandbox_id=backend.id)
        assert again.execute("cat /home/user/note.txt").output.strip() == "hello"
    finally:
        provider.delete(sandbox_id=backend.id)
    assert Maritime().sandboxes.get(backend.id).state == "ended"
    with pytest.raises(SandboxNotFoundError):
        provider.get_or_create(sandbox_id=backend.id)
    provider.delete(sandbox_id=backend.id)  # deleting twice is fine


def test_new_sandbox_from_a_saved_snapshot() -> None:
    client = Maritime()
    provider = MaritimeProvider()
    name = f"langchain-maritime-test-{uuid.uuid4().hex[:8]}"
    source = client.sandboxes.create(idle_timeout_seconds=300, on_idle="kill")
    restored = None
    try:
        source.run("echo from-the-snapshot > /home/user/marker.txt")
        source.save(name)
        restored = provider.get_or_create(snapshot=name, idle_timeout_seconds=300, on_idle="kill")
        assert restored.execute("cat /home/user/marker.txt").output.strip() == "from-the-snapshot"
    finally:
        source.kill()
        if restored is not None:
            provider.delete(sandbox_id=restored.id)
        client.snapshots.delete(name)
