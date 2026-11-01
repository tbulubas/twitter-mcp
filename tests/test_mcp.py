# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

"""The MCP adapter, exercised through an in-memory FastMCP client."""

import anyio
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from twittermcp.core import xpost
from twittermcp.mcp_server import mcp


def call(name, args):
    async def go():
        async with Client(mcp) as client:
            return await client.call_tool(name, args)
    return anyio.run(go)


def test_tools_are_listed():
    async def go():
        async with Client(mcp) as client:
            return {t.name for t in await client.list_tools()}
    assert anyio.run(go) == {"get_post", "transcribe_post", "analyze_post", "recent_analyses"}


def test_get_post_tool(monkeypatch, syndication_post):
    monkeypatch.setattr(xpost, "fetch_post", lambda pid: xpost.parse_syndication(syndication_post))
    result = call("get_post", {"url": "https://x.com/examplelab/status/1850000000000000001"})
    assert result.data["author_handle"] == "examplelab"
    assert result.data["media"][1]["kind"] == "video"


def test_errors_carry_a_code():
    with pytest.raises(ToolError, match="invalid_url"):
        call("get_post", {"url": "https://example.org/nothing"})


def test_transcribe_post_without_video(monkeypatch, syndication_post):
    syndication_post["mediaDetails"] = []
    monkeypatch.setattr(xpost, "fetch_post", lambda pid: xpost.parse_syndication(syndication_post))
    assert call("transcribe_post", {"url": "1850000000000000001"}).data == {
        "post_id": "1850000000000000001", "videos": []}
