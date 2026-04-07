import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent

load_dotenv()

_REPO_ROOT = Path(__file__).resolve().parent
_MANIM_SERVER = _REPO_ROOT / "manim_server.py"


async def main():
    client = MultiServerMCPClient(
        {
            "manim-server": {
                "transport": "stdio",
                "command": sys.executable,
                "args": [str(_MANIM_SERVER)],
                "env": {"MANIM_EXECUTABLE": "manim"},
                "cwd": str(_REPO_ROOT),
            }
        }
    )

    tools = await client.get_tools()
    agent = create_agent(
        "openai:gpt-4o",
        tools,
    )
    response = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "generate a manim animation that shows a circle growing and shrinking"}]}
    )
    print(response)

if __name__ == "__main__":
    asyncio.run(main())
    