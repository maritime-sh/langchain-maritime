"""A Deep Agent whose files and shell live on a Maritime sandbox.

pip install langchain-maritime langchain-openai
export MARITIME_API_KEY=...       # maritime.sh/settings/api-keys
export OPENAI_API_KEY=...         # an OpenAI key, or a Maritime LLM token
export OPENAI_BASE_URL=https://api.maritime.sh/api/llm/v1   # only for Maritime LLM
python examples/deep_agent.py
"""

import os

from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI

from langchain_maritime import MaritimeSandbox

TASK = (
    "In /home/user/project, write primes.py that prints the first 10 prime numbers, one per line. "
    "Run it, then tell me the output and the Python version on this machine."
)


def main() -> None:
    backend = MaritimeSandbox.create(idle_timeout_seconds=600, on_idle="kill")
    print(f"sandbox {backend.id}")
    try:
        agent = create_deep_agent(
            model=ChatOpenAI(model=os.environ.get("MODEL", "gpt-5.4")),
            system_prompt="You work on a Linux machine. Use your file and shell tools, then answer briefly.",
            backend=backend,
        )
        result = agent.invoke({"messages": [{"role": "user", "content": TASK}]})
        for message in result["messages"]:
            for call in getattr(message, "tool_calls", None) or []:
                print(f"> {call['name']} {call['args']}")
        print("\n" + result["messages"][-1].content)
        print("\nOn the sandbox:\n" + backend.execute("cat /home/user/project/primes.py").output)
    finally:
        backend.kill()


if __name__ == "__main__":
    main()
