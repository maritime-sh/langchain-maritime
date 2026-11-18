<p align="center">
  <a href="https://maritime.sh">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="assets/maritime-mark-white.png">
      <img src="assets/maritime-mark-black.png" width="64" alt="Maritime">
    </picture>
  </a>
</p>

<h1 align="center">langchain-maritime</h1>

<p align="center"><a href="https://pypi.org/project/langchain-maritime/"><img src="https://img.shields.io/pypi/v/langchain-maritime?style=flat-square&color=2563eb" alt="PyPI"></a> <a href="https://pypi.org/project/langchain-maritime/"><img src="https://img.shields.io/pypi/pyversions/langchain-maritime?style=flat-square" alt="Python versions"></a> <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-0a0a0a?style=flat-square" alt="MIT license"></a> <a href="https://github.com/maritime-sh/langchain-maritime/actions/workflows/test.yml"><img src="https://img.shields.io/github/actions/workflow/status/maritime-sh/langchain-maritime/test.yml?branch=main&style=flat-square&label=tests" alt="Tests"></a> <a href="https://maritime.sh/docs"><img src="https://img.shields.io/badge/docs-maritime.sh-0a0a0a?style=flat-square" alt="Docs"></a> <a href="https://discord.gg/wvPAvXNZqm"><img src="https://img.shields.io/badge/Discord-join-5865F2?style=flat-square&logo=discord&logoColor=white" alt="Discord"></a></p>

<p align="center">
  <b>Run <a href="https://github.com/langchain-ai/deepagents">Deep Agents</a> on a real cloud computer from <a href="https://maritime.sh">Maritime</a>.</b><br>
  Every file read, edit, search and shell command happens in the agent's own Linux sandbox, never on your machine.
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> ·
  <a href="#deep-agents-code">Deep Agents Code</a> ·
  <a href="#options">Options</a> ·
  <a href="#tested">Tested</a> ·
  <a href="https://github.com/maritime-sh/agents">More agents on Maritime</a>
</p>

## Quickstart

```bash
pip install langchain-maritime langchain-openai
export MARITIME_API_KEY=mk_...     # maritime.sh/settings/api-keys
export OPENAI_API_KEY=sk-...
```

```python
from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI

from langchain_maritime import MaritimeSandbox

backend = MaritimeSandbox.create(idle_timeout_seconds=600)
try:
    agent = create_deep_agent(model=ChatOpenAI(model="gpt-5.4"), backend=backend)
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Write primes.py that prints 10 primes, run it, show me the output.",
                }
            ]
        }
    )
    print(result["messages"][-1].content)
finally:
    backend.kill()
```

`MaritimeSandbox.create()` starts a fresh sandbox in a few seconds. The agent's `ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep` and `execute` tools all run inside it.

Already have a sandbox? Wrap it:

```python
from maritime import Maritime

sandbox = Maritime().sandboxes.get("sbx-...")
backend = MaritimeSandbox(sandbox=sandbox)
```

The runnable version is [`examples/deep_agent.py`](examples/deep_agent.py). No OpenAI account? [Maritime LLM](https://maritime.sh/docs/llm) is OpenAI-compatible: set `OPENAI_BASE_URL=https://api.maritime.sh/api/llm/v1` and use your Maritime LLM token as `OPENAI_API_KEY`.

## Deep Agents Code

Installing this package adds a `maritime` sandbox to [Deep Agents Code](https://github.com/langchain-ai/deepagents/tree/main/libs/code). No config needed:

```bash
dcode install langchain-maritime --package
export MARITIME_API_KEY=mk_...
dcode --sandbox maritime
```

Deep Agents Code starts a sandbox for the session, works in `/home/user`, and ends the sandbox when you quit. To keep working in the same machine, pass its id with `--sandbox-id sbx-...`. To start from a snapshot you saved, pass `--sandbox-snapshot-name my-snapshot`.

To set Maritime options for every session, declare the provider in `~/.deepagents/config.toml`. Deep Agents Code reads `params` only from a declared provider, so keep the first three lines:

```toml
[sandboxes.providers.maritime]
class_path = "langchain_maritime.dcode:MaritimeProvider"
working_dir = "/home/user"
supports_snapshot_name = true

[sandboxes.providers.maritime.params]
size = "large"
idle_timeout_seconds = 3600
```

## What the agent gets

- **Its own Linux machine.** Ubuntu 24.04 with Python 3.12, Node, git and curl, 2 vCPUs, 4 GiB of memory and 12 GiB of disk by default, up to 16 vCPUs and 64 GiB.
- **Real isolation.** Each sandbox is a microVM with its own kernel, filesystem, network and processes.
- **Root when it needs it.** Commands run as `user`, with passwordless `sudo` for installs.
- **Limits that clean up after you.** An idle timeout pauses or ends a forgotten sandbox, and `time_limit_seconds` ends it no matter what.

## Options

`MaritimeSandbox.create()` takes any [Maritime sandbox option](https://maritime.sh/docs/sandboxes):

| Option | Default | What it does |
| --- | --- | --- |
| `from_` | `base` | A saved snapshot, a template, or a public image to start from. |
| `size` | `small` | A preset: `small`, `medium`, `large` or `xlarge`. |
| `vcpu`, `memory_mib`, `disk_gib` | from `size` | Override the preset. |
| `env` | none | Environment variables for every command. |
| `idle_timeout_seconds` | Maritime's default | How long without activity before `on_idle` applies. |
| `on_idle` | `pause` | `pause` keeps the disk and resumes on the next call. `kill` ends the sandbox. |
| `time_limit_seconds` | none | End the sandbox this long after it starts. |
| `metadata` | none | Labels you can filter on when you list sandboxes. |

The backend itself takes `timeout`, the default seconds a command may run (30 minutes). A timeout of `0` waits as long as Maritime allows.

## Behavior

- Commands run with `bash -lc`. Output is stdout followed by `<stderr>...</stderr>` when there is any.
- A command that runs out of time returns exit code `124` with the output it printed so far.
- File errors use Deep Agents' codes (`file_not_found`, `is_directory`, `invalid_path`, `permission_denied`). Anything else, such as an ended sandbox or a billing limit, keeps Maritime's own message so the agent sees what really went wrong.
- Maritime's file API acts as the machine's administrator, so `download_files` can read a file the shell user cannot.

## Tested

The [Deep Agents standard sandbox suite](https://github.com/langchain-ai/langchain/tree/master/libs/standard-tests) runs against a real Maritime sandbox:

```bash
MARITIME_API_KEY=mk_... uv run pytest -m live
```

On 2026-11-17, with `deepagents` 0.7.39, `maritime` 0.12 and `langchain-tests` 1.1.9, 77 of the 86 standard tests pass. The other 9 are marked as expected failures in [`conftest.py`](tests/integration_tests/conftest.py), each with its reason:

- 7 glob and write tests: `langchain-tests` 1.1.9 expects relative glob paths and a `write` that refuses existing files, while `deepagents` 0.7.x returns absolute paths and overwrites. A plain local `BaseSandbox` fails them the same way.
- 2 large-output tests call `python`, and the Maritime base image ships `python3` only.

The live tests also cover the Deep Agents Code provider: create, reconnect by id, delete, and a new sandbox from a saved snapshot.

The unit tests run without an account. They swap only the network calls, so commands really run and Deep Agents' read, write, edit and ls helpers execute for real:

```bash
uv run pytest
```

## Compatibility

| Package | Versions |
| --- | --- |
| Python | 3.11 to 3.14 |
| `deepagents` | 0.7.34 and later 0.7.x |
| `deepagents-code` (optional) | 0.2.5 and later, on Python 3.14 |
| `maritime` | 0.11.x and 0.12.x |

## License

[MIT](LICENSE), from [Maritime](https://maritime.sh).
