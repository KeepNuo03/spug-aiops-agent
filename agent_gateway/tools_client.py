"""MCP client: calls the tools exposed by mcp_server over streamable HTTP."""

import os
from typing import Any

from mcp import Client

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://mcp_server:8765/mcp")


async def call_tool(name: str, arguments: dict[str, Any]) -> Any:
    async with Client(MCP_SERVER_URL) as client:
        result = await client.call_tool(name, arguments)
    if result.is_error:
        raise RuntimeError(f"tool {name} failed: {result.content}")
    if result.structured_content is None:
        # Tools must declare a return model; without one the payload arrives as plain text only.
        raise RuntimeError(f"tool {name} returned no structured content")
    return result.structured_content
