"""List the tools a configured MCP server exposes (use it to fill `upwork_live.tool_map`).

    python -m agent.tools_listing portfolio
    UPWORK_TOKEN=... python -m agent.tools_listing upwork
"""
from __future__ import annotations

import asyncio
import os
import sys

from agent.config import load_config


async def main(server: str):
    from langchain_mcp_adapters.client import MultiServerMCPClient

    cfg = load_config()
    if server == "upwork":
        conn = {"transport": "streamable_http", "url": cfg["marketplace"]["upwork_live"]["url"],
                "headers": {"Authorization": f"Bearer {os.environ['UPWORK_TOKEN']}"}}
    else:
        spec = cfg["mcp"]["servers"][server]
        conn = {"transport": "stdio", "command": spec["command"], "args": spec["args"]}
    tools = await MultiServerMCPClient({server: conn}).get_tools()
    for t in tools:
        print(f"{t.name:28} {(t.description or '').splitlines()[0][:90]}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "portfolio"))
