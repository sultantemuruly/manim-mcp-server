import asyncio
import sys
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()

_REPO_ROOT = Path(__file__).resolve().parent
_MANIM_SERVER = _REPO_ROOT / "manim_server.py"
_MANIM_TMP = _REPO_ROOT / "media" / "manim_tmp"


def _max_mp4_mtime(root: Path) -> float:
    if not root.exists():
        return 0.0
    latest = 0.0
    for p in root.rglob("*.mp4"):
        if p.is_file():
            latest = max(latest, p.stat().st_mtime)
    return latest


def _newest_mp4_after(root: Path, before_mtime: float) -> str | None:
    if not root.exists():
        return None
    candidates = [
        p
        for p in root.rglob("*.mp4")
        if p.is_file() and p.stat().st_mtime > before_mtime
    ]
    if not candidates:
        return None
    best = max(candidates, key=lambda p: p.stat().st_mtime)
    return str(best.resolve())


def _extract_reply(messages: list) -> str:
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        content = msg.content
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
            text = "".join(parts).strip()
            if text:
                return text
    return "No assistant text was returned."


async def run_agent_async(user_prompt: str) -> tuple[str, str | None]:
    prompt = (user_prompt or "").strip()
    if not prompt:
        return (
            "Please describe the animation you want (e.g. “a circle growing and shrinking”).",
            None,
        )

    before = _max_mp4_mtime(_MANIM_TMP)

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

    try:
        tools = await client.get_tools()
        agent = create_agent("openai:gpt-4o", tools)
        response = await agent.ainvoke(
            {"messages": [{"role": "user", "content": prompt}]}
        )
    except Exception as e:
        return (f"Something went wrong while running the agent: {e}", None)

    messages = response.get("messages", [])
    text = _extract_reply(messages)
    video_path = _newest_mp4_after(_MANIM_TMP, before)
    return (text, video_path)


def run_agent(user_prompt: str) -> tuple[str, str | None]:
    """Sync entrypoint for Gradio (runs coroutine in a fresh event loop)."""
    return asyncio.run(run_agent_async(user_prompt))


def build_demo() -> gr.Interface:
    return gr.Interface(
        fn=run_agent,
        inputs=gr.Textbox(
            label="What should Manim show?",
            placeholder="e.g. A blue circle that grows then shrinks",
            lines=3,
        ),
        outputs=[
            gr.Textbox(label="Assistant reply", lines=12),
            gr.Video(label="Rendered video"),
        ],
        title="Manim MCP agent",
        description="Uses OpenAI and your local Manim MCP server to turn a short description into code, render it, and show the latest video from this run.",
        api_name="manim_animation",
    )


if __name__ == "__main__":
    build_demo().queue().launch()
