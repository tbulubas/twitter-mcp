# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

"""MCP adapter: exposes the core use cases as tools. No logic of its own.

Runs over stdio (Claude Desktop / Claude Code start it as a subprocess) or
over Streamable HTTP on 127.0.0.1. The HTTP endpoint has no authentication
yet, so it must not be exposed through a tunnel until OAuth is added.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

import anyio
import anyio.from_thread
import anyio.to_thread
from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError

from twittermcp.core import db, pipeline, xpost

INSTRUCTIONS = """\
Tools for analyzing single posts on X.com (twitter.com) by URL. Analysis runs
locally: videos are transcribed with Whisper and summarized by a local Gemma
model, so analyze_post can take several minutes for long videos; results are
cached, and a repeated call returns at once. Use get_post for the plain text
and media list, transcribe_post for the exact words with timestamps, and
analyze_post for a summary, key points and who said what.
"""


@asynccontextmanager
async def lifespan(_server: FastMCP):
    db.init_db()
    yield {}


mcp = FastMCP("TwitterMcp", instructions=INSTRUCTIONS, lifespan=lifespan)


async def _run(ctx: Context | None, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run a blocking core call in a worker thread; its progress lines become MCP log messages."""
    def progress(msg: str) -> None:
        if ctx is not None:
            anyio.from_thread.run(ctx.info, msg)

    try:
        if "progress" in kwargs:
            kwargs["progress"] = progress
        return await anyio.to_thread.run_sync(lambda: fn(*args, **kwargs))
    except (xpost.PostError, pipeline.OllamaUnavailable) as e:
        raise ToolError(f"{e.code}: {e}") from e


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
async def get_post(url: str) -> dict:
    """Text, author, date and media of an X.com post. Fast; no LLM involved.

    Args:
        url: link to the post (x.com or twitter.com), or its numeric id
    """
    post = await _run(None, pipeline.get_post, url)
    return post.to_dict()


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
async def transcribe_post(url: str, ctx: Context) -> dict:
    """Word-for-word transcript of the videos in an X.com post, with [mm:ss] timestamps.

    Args:
        url: link to the post (x.com or twitter.com), or its numeric id
    """
    post = await _run(ctx, pipeline.get_post, url)
    if not post.has_video:
        return {"post_id": post.id, "videos": []}
    ts = await _run(ctx, pipeline.transcripts, post, progress=None)
    return {
        "post_id": post.id,
        "videos": [{"language": t.language, "duration_s": t.duration_s, "transcript": t.timestamped()}
                   for t in ts],
    }


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
async def analyze_post(url: str, ctx: Context, question: str | None = None, language: str = "en",
                       refresh: bool = False) -> dict:
    """Summary, key points, speakers with their statements, topics and claims worth
    checking for an X.com post, including what is said in its videos and shown in its images.

    Args:
        url: link to the post (x.com or twitter.com), or its numeric id
        question: optional question about the post, answered in the 'answer' field
        language: language code of the output, e.g. en, sk, de
        refresh: ignore cached results and analyze again
    """
    return await _run(ctx, pipeline.analyze_post, url, question=question, language=language,
                      refresh=refresh, progress=None)


@mcp.tool(annotations={"readOnlyHint": True})
async def recent_analyses(limit: int = 20) -> list[dict]:
    """Posts analyzed recently (from the local cache), newest first, with their summaries."""
    return await anyio.to_thread.run_sync(db.recent_analyses, limit)
