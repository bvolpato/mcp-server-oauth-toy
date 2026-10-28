import pytest
from mcp import Client

from mcp_server_oauth_toy import server


@pytest.mark.asyncio
async def test_mcp_tools_are_registered_and_callable() -> None:
    server._request_user_name = "Ada"
    try:
        async with Client(server.mcp_server) as client:
            tools = await client.list_tools()
            assert {tool.name for tool in tools.tools} == {"whoami", "echo"}

            result = await client.call_tool("echo", {"message": "hello"})
            assert result.content[0].text == "Ada says: hello"
    finally:
        server._request_user_name = None
