"""
Smoke test for the Manim MCP server.

Spawns manim_server.py as a stdio MCP subprocess, lists tools,
and calls execute_manim_code with a minimal scene to verify the
full round-trip works.
"""

import asyncio
import sys
import os

import mcp.types as mcp_types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "manim_server.py")

SAMPLE_SCENE = '''\
from manim import *

class HelloCircle(Scene):
    def construct(self):
        circle = Circle(color=BLUE)
        self.play(Create(circle))
        self.wait(1)
'''


async def main():
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[SERVER_SCRIPT],
        env={**os.environ},
    )

    print("Starting MCP server …")
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            init = await session.initialize()
            print(f"Server: {init.serverInfo.name} v{init.serverInfo.version}")
            print(f"Protocol: {init.protocolVersion}\n")

            # --- list tools ---
            tools_result = await session.list_tools()
            print(f"Available tools ({len(tools_result.tools)}):")
            for tool in tools_result.tools:
                print(f"  - {tool.name}: {tool.description}")
            print()

            # --- call execute_manim_code ---
            print("Calling execute_manim_code with a simple scene …")
            result = await session.call_tool(
                "execute_manim_code",
                {"manim_code": SAMPLE_SCENE},
            )
            for block in result.content:
                if isinstance(block, mcp_types.TextContent):
                    print(f"  [{block.type}] {block.text}")
                elif isinstance(block, mcp_types.ImageContent):
                    print(f"  [{block.type}] mime={block.mimeType} data_len={len(block.data)}")
                elif isinstance(block, mcp_types.AudioContent):
                    print(f"  [{block.type}] mime={block.mimeType} data_len={len(block.data)}")
                elif isinstance(block, mcp_types.ResourceLink):
                    print(f"  [{block.type}] {block.uri} ({block.name})")
                elif isinstance(block, mcp_types.EmbeddedResource):
                    print(f"  [{block.type}] {block.resource}")
                else:
                    print(f"  [unknown] {block!r}")

            print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
