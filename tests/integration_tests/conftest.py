"""Known failures in the standard suite, each one checked to be outside this package.

They are strict expected failures: if upstream or the Maritime image changes so
one passes, the run fails and the entry here has to go.
"""

from __future__ import annotations

import pytest

# langchain-tests 1.1.9 expects glob() to return relative paths and write() to
# refuse an existing file. deepagents 0.7.x's BaseSandbox returns absolute paths
# and overwrites. A plain local BaseSandbox with no Maritime code fails these
# exactly the same way.
UPSTREAM_MISMATCH = {
    "test_glob",
    "test_glob_basic_pattern",
    "test_glob_with_directories",
    "test_glob_hidden_files_explicitly",
    "test_glob_with_character_class",
    "test_glob_with_question_mark",
    "test_write_existing_file_fails",
}

# These call `python`, and Maritime's base image only ships `python3`.
NO_PYTHON_ALIAS = {
    "test_execute_large_stdout_payload",
    "test_aexecute_large_stdout_payload",
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        name = getattr(item, "originalname", item.name)
        if "TestMaritimeSandboxStandard" not in item.nodeid:
            continue
        if name in UPSTREAM_MISMATCH:
            item.add_marker(
                pytest.mark.xfail(strict=True, reason="langchain-tests 1.1.9 vs deepagents 0.7.x")
            )
        elif name in NO_PYTHON_ALIAS:
            item.add_marker(pytest.mark.xfail(strict=True, reason="the base image has python3 but no python"))
