# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

"""Command line interface: run the MCP server, or use the core directly."""

from __future__ import annotations

import argparse
import json
import sys

DEFAULT_PORT = 8600


def _print(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _progress(msg: str) -> None:
    print(f"... {msg}", file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="twittermcp", description="Local analysis of X.com posts.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="run the MCP server (stdio by default)")
    p_serve.add_argument("--http", action="store_true", help="Streamable HTTP instead of stdio")
    # 127.0.0.1 only: the HTTP endpoint has no authentication yet
    p_serve.add_argument("--host", default="127.0.0.1", help="interface to bind (default 127.0.0.1)")
    p_serve.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port (default {DEFAULT_PORT})")

    p_post = sub.add_parser("post", help="print a post's text and media as JSON")
    p_post.add_argument("url")

    p_tr = sub.add_parser("transcribe", help="print the timestamped transcript of a post's videos")
    p_tr.add_argument("url")

    p_an = sub.add_parser("analyze", help="summarize a post with its videos and images")
    p_an.add_argument("url")
    p_an.add_argument("-q", "--question", help="a question about the post")
    p_an.add_argument("-l", "--lang", default="en", help="output language code (default en)")
    p_an.add_argument("--refresh", action="store_true", help="ignore cached results")

    args = parser.parse_args(argv)

    # UTF-8 also when redirected to a file, not the Windows ANSI code page
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if args.command == "serve":
        from twittermcp.mcp_server import mcp

        if args.http:
            mcp.run(transport="http", host=args.host, port=args.port)
        else:
            mcp.run()
        return

    from twittermcp.core import db, pipeline, xpost

    db.init_db()
    try:
        if args.command == "post":
            _print(pipeline.get_post(args.url).to_dict())
        elif args.command == "transcribe":
            post = pipeline.get_post(args.url)
            for i, t in enumerate(pipeline.transcripts(post, _progress), 1):
                print(f"== video {i} ({t.language}, {t.duration_s:.0f} s)")
                print(t.timestamped())
        elif args.command == "analyze":
            _print(pipeline.analyze_post(args.url, question=args.question, language=args.lang,
                                         refresh=args.refresh, progress=_progress))
    except (xpost.PostError, pipeline.OllamaUnavailable) as e:
        sys.exit(f"error: {e.code}: {e}")
