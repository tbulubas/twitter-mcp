# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

"""Shared fixtures. Tests never touch data/, the network, Ollama or Whisper."""

import copy

import pytest
import requests

from twittermcp.core import config, db, gemma

# an invented post in the shape of the syndication endpoint's JSON
SYNDICATION_POST = {
    "__typename": "Tweet",
    "id_str": "1850000000000000001",
    "lang": "en",
    "created_at": "2026-10-30T08:15:00.000Z",
    "display_text_range": [0, 62],
    "text": "Our new paper on local LLMs is out: https://t.co/abc123 Thread https://t.co/media1",
    "entities": {"urls": [{"url": "https://t.co/abc123", "expanded_url": "https://example.org/paper"}]},
    "user": {"name": "Example Lab", "screen_name": "examplelab"},
    "favorite_count": 42,
    "conversation_count": 3,
    "mediaDetails": [
        {"type": "photo", "media_url_https": "https://pbs.twimg.com/media/AAA.jpg", "ext_alt_text": "A chart"},
        {
            "type": "video",
            "media_url_https": "https://pbs.twimg.com/ext_tw_video_thumb/1/pu/img/BBB.jpg",
            "video_info": {
                "duration_millis": 95000,
                "variants": [
                    {"content_type": "application/x-mpegURL", "url": "https://video.twimg.com/pl.m3u8"},
                    {"content_type": "video/mp4", "bitrate": 832000, "url": "https://video.twimg.com/low.mp4"},
                    {"content_type": "video/mp4", "bitrate": 2176000, "url": "https://video.twimg.com/high.mp4"},
                ],
            },
        },
    ],
    "quoted_tweet": {
        "id_str": "1849999999999999999",
        "text": "What runs on a laptop GPU today?",
        "created_at": "2026-10-29T18:00:00.000Z",
        "user": {"name": "Someone", "screen_name": "someone"},
    },
}


@pytest.fixture
def syndication_post():
    return copy.deepcopy(SYNDICATION_POST)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "data" / "test.db")
    monkeypatch.delenv("TWITTERMCP_COOKIES", raising=False)
    monkeypatch.delenv("TWITTERMCP_COOKIES_BROWSER", raising=False)
    # no Ollama in tests: the deterministic paths must work on their own
    monkeypatch.setattr(gemma, "available", lambda: False)

    def no_network(*args, **kwargs):
        raise AssertionError("tests must not use the network")

    monkeypatch.setattr(requests.Session, "request", no_network)
    db.init_db()
