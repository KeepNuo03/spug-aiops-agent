import pytest
from mcp.types import CallToolResult, TextContent

import tools_client
from tools_client import call_tool


class FakeClient:
    def __init__(self, result: CallToolResult):
        self._result = result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def call_tool(self, name, arguments):
        return self._result


@pytest.fixture
def served(monkeypatch):
    def serve(result: CallToolResult):
        monkeypatch.setattr(tools_client, "Client", lambda url: FakeClient(result))

    return serve


async def test_structured_content_is_returned(served):
    served(CallToolResult(content=[], structured_content={"output": "load average: 0.1"}))
    assert await call_tool("exec_command", {}) == {"output": "load average: 0.1"}


async def test_tool_error_is_raised(served):
    served(CallToolResult(content=[TextContent(type="text", text="boom")], is_error=True))
    with pytest.raises(RuntimeError, match="failed"):
        await call_tool("exec_command", {})


async def test_missing_structured_content_is_an_error(served):
    served(CallToolResult(content=[TextContent(type="text", text='{"output": "ok"}')]))
    with pytest.raises(RuntimeError, match="no structured content"):
        await call_tool("exec_command", {})
