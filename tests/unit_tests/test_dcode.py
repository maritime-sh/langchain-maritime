from __future__ import annotations

import importlib.metadata

import pytest

pytest.importorskip("deepagents_code", reason="Deep Agents Code is not installed (it needs Python 3.14)")
from deepagents_code.integrations.sandbox_provider import SandboxNotFoundError
from deepagents_code.integrations.sandbox_registry import SandboxRegistry
from maritime import MaritimeSandboxError

from langchain_maritime import MaritimeSandbox
from langchain_maritime.dcode import MaritimeProvider

from .fakes import FakeMaritime


@pytest.fixture
def fake() -> FakeMaritime:
    return FakeMaritime()


@pytest.fixture
def provider(fake: FakeMaritime) -> MaritimeProvider:
    return MaritimeProvider(client=fake)  # type: ignore[arg-type]


def test_entry_point_is_registered() -> None:
    (entry,) = [
        e
        for e in importlib.metadata.entry_points(group="deepagents_code.sandbox_providers")
        if e.name == "maritime"
    ]
    assert entry.load() is MaritimeProvider


def test_deep_agents_code_lists_and_describes_the_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARITIME_API_KEY", "mk_test")
    registry = SandboxRegistry.load()
    assert "maritime" in registry.available_providers()
    meta = registry.provider_metadata("maritime")
    assert meta.working_dir == "/home/user"
    assert meta.supports_snapshot_name and meta.supports_sandbox_id
    assert meta.install is not None and meta.install.command(in_app=False) == (
        "dcode install langchain-maritime --package"
    )
    assert isinstance(registry.create_provider("maritime"), MaritimeProvider)


def test_needs_an_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MARITIME_API_KEY", raising=False)
    monkeypatch.delenv("DEEPAGENTS_CODE_MARITIME_API_KEY", raising=False)
    with pytest.raises(ValueError, match="MARITIME_API_KEY"):
        MaritimeProvider()


def test_prefers_the_deepagents_code_key(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str | None] = []
    monkeypatch.setattr("langchain_maritime.dcode.Maritime", lambda api_key=None: seen.append(api_key))
    monkeypatch.setenv("MARITIME_API_KEY", "mk_general")
    monkeypatch.setenv("DEEPAGENTS_CODE_MARITIME_API_KEY", "mk_dcode")
    MaritimeProvider()
    assert seen == ["mk_dcode"]


def test_creates_with_safe_defaults(provider: MaritimeProvider, fake: FakeMaritime) -> None:
    backend = provider.get_or_create()
    assert isinstance(backend, MaritimeSandbox)
    (sandbox,) = fake.sandboxes.created
    assert sandbox.create_kwargs == {
        "from_": None,
        "idle_timeout_seconds": 1800,
        "on_idle": "pause",
        "metadata": {"created_by": "deepagents-code"},
    }


def test_config_params_and_snapshot_are_forwarded(provider: MaritimeProvider, fake: FakeMaritime) -> None:
    provider.get_or_create(snapshot="py-ready", size="large", env={"A": "1"}, metadata={"team": "x"})
    kwargs = fake.sandboxes.created[0].create_kwargs
    assert kwargs["from_"] == "py-ready"
    assert kwargs["size"] == "large"
    assert kwargs["env"] == {"A": "1"}
    assert kwargs["metadata"] == {"team": "x", "created_by": "deepagents-code"}


def test_rejects_unknown_params(provider: MaritimeProvider, fake: FakeMaritime) -> None:
    with pytest.raises(TypeError, match="snapshot_image"):
        provider.get_or_create(snapshot_image="python:3.12")
    assert fake.sandboxes.created == []


def test_connects_to_an_existing_sandbox(provider: MaritimeProvider, fake: FakeMaritime) -> None:
    existing = fake.sandboxes.create()
    backend = provider.get_or_create(sandbox_id=existing.id)
    assert backend.id == existing.id
    assert len(fake.sandboxes.created) == 1


def test_missing_or_ended_sandbox_is_not_found(provider: MaritimeProvider, fake: FakeMaritime) -> None:
    with pytest.raises(SandboxNotFoundError):
        provider.get_or_create(sandbox_id="sbx-nope")
    ended = fake.sandboxes.create()
    ended.state = "ended"
    with pytest.raises(SandboxNotFoundError):
        provider.get_or_create(sandbox_id=ended.id)


def test_snapshot_with_sandbox_id_is_refused(provider: MaritimeProvider, fake: FakeMaritime) -> None:
    existing = fake.sandboxes.create()
    with pytest.raises(ValueError):
        provider.get_or_create(sandbox_id=existing.id, snapshot="x")


def test_delete_ends_the_sandbox_and_tolerates_gone_ones(
    provider: MaritimeProvider, fake: FakeMaritime
) -> None:
    sandbox = fake.sandboxes.create()
    provider.delete(sandbox_id=sandbox.id)
    assert sandbox.state == "ended"
    provider.delete(sandbox_id="sbx-already-gone")


def test_delete_surfaces_real_failures(provider: MaritimeProvider, fake: FakeMaritime) -> None:
    def broken(_: str) -> None:
        raise MaritimeSandboxError(401, code="unauthenticated", message="bad key")

    fake.sandboxes.get = broken  # type: ignore[method-assign]
    with pytest.raises(MaritimeSandboxError):
        provider.delete(sandbox_id="sbx-1")


async def test_async_wrappers(provider: MaritimeProvider, fake: FakeMaritime) -> None:
    backend = await provider.aget_or_create()
    await provider.adelete(sandbox_id=backend.id)
    assert fake.sandboxes.created[0].state == "ended"
