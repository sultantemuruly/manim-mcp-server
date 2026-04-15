import asyncio
import os
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import StreamableHttpConnection

load_dotenv()

_REPO_ROOT = Path(__file__).resolve().parent
_HOSTED_MCP_URL = (os.environ.get("HOSTED_MCP_URL") or "").strip()
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


def _format_agent_error(exc: BaseException) -> str:
    """Expand TaskGroup/ExceptionGroup wrappers so the UI shows the real failure."""
    if isinstance(exc, BaseExceptionGroup):
        parts: list[str] = [str(exc).strip()]
        for sub in exc.exceptions:
            parts.append(_format_agent_error(sub))
        return "\n".join(parts)
    return f"{type(exc).__name__}: {exc}".strip()


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

    if not _HOSTED_MCP_URL:
        return (
            "Set HOSTED_MCP_URL to your Manim MCP streamable HTTP endpoint "
            "(e.g. http://host:8000/mcp).",
            None,
        )

    before_mtime = _max_mp4_mtime(_MANIM_TMP)

    client = MultiServerMCPClient({
        "manim-server": StreamableHttpConnection(
            transport="streamable_http",
            url=_HOSTED_MCP_URL,
        ),
    })

    try:
        tools = await client.get_tools()
        agent = create_agent("openai:gpt-4o", tools)
        response = await agent.ainvoke(
            {"messages": [{"role": "user", "content": prompt}]}
        )
    except Exception as e:
        detail = _format_agent_error(e)
        return (f"Something went wrong while running the agent:\n{detail}", None)

    messages = response.get("messages", [])
    text = _extract_reply(messages)
    video_path = _newest_mp4_after(_MANIM_TMP, before_mtime)
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
        description=(
            "Uses OpenAI and a hosted Manim MCP server (streamable HTTP) to turn a short description "
            "into code and render it. Set HOSTED_MCP_URL. Video preview appears when new renders land "
            "under media/manim_tmp locally."
        ),
        api_name="manim_animation",
    )


if __name__ == "__main__":
    build_demo().queue().launch()
