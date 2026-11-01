# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

"""Paths and settings, all overridable by environment variables."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# downloaded media and the cache database; gitignored
DATA_DIR = Path(os.environ.get("TWITTERMCP_DATA", PROJECT_ROOT / "data"))


def media_dir(post_id: str) -> Path:
    return DATA_DIR / "media" / post_id


def cookie_options() -> dict:
    """yt-dlp options for the user's X.com session, if configured.

    TWITTERMCP_COOKIES is a Netscape cookies.txt file, TWITTERMCP_COOKIES_BROWSER
    a browser name for yt-dlp (firefox works on Windows; Chrome encrypts its
    cookies so yt-dlp cannot read them). Without either, only public posts work.
    The cookies are never read or logged by this project, only passed to yt-dlp.
    """
    if path := os.environ.get("TWITTERMCP_COOKIES"):
        return {"cookiefile": path}
    if browser := os.environ.get("TWITTERMCP_COOKIES_BROWSER"):
        return {"cookiesfrombrowser": (browser,)}
    return {}
