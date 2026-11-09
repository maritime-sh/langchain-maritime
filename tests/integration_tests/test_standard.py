"""The Deep Agents standard sandbox suite, on a real Maritime sandbox.

Run with: MARITIME_API_KEY=mk_... pytest -m live
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from deepagents.backends.protocol import SandboxBackendProtocol
from langchain_tests.integration_tests import SandboxIntegrationTests

from langchain_maritime import MaritimeSandbox

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("MARITIME_API_KEY"), reason="needs MARITIME_API_KEY"),
]


class TestMaritimeSandboxStandard(SandboxIntegrationTests):
    @pytest.fixture(scope="class")
    def sandbox(self) -> Iterator[SandboxBackendProtocol]:
        backend = MaritimeSandbox.create(
            idle_timeout_seconds=600, on_idle="kill", time_limit_seconds=3600, metadata={"test": "standard"}
        )
        try:
            yield backend
        finally:
            backend.kill()
