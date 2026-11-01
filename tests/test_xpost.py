# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

import pytest

from twittermcp.core import xpost
from twittermcp.core.xpost import Post


@pytest.mark.parametrize("url", [
    "https://x.com/examplelab/status/1850000000000000001",
    "https://twitter.com/examplelab/status/1850000000000000001?s=20&t=abc",
    "x.com/examplelab/status/1850000000000000001/photo/1",
    "https://mobile.twitter.com/examplelab/statuses/1850000000000000001",
    "https://x.com/i/web/status/1850000000000000001",
    "https://fxtwitter.com/examplelab/status/1850000000000000001",
    "  1850000000000000001 ",
])
def test_post_id(url):
    assert xpost.post_id(url) == "1850000000000000001"


@pytest.mark.parametrize("url", ["https://x.com/examplelab", "https://example.org/status/1", ""])
def test_post_id_rejects_other_urls(url):
    with pytest.raises(xpost.InvalidPostUrl):
        xpost.post_id(url)


# reference values from Node: ((Number(id) / 1e15) * Math.PI).toString(36).replace(/(0+|\.)/g, "")
@pytest.mark.parametrize("pid, token", [
    ("20", "6dq1a2xwd93"),
    ("1585341984679469056", "3uchycv2wqc"),
    ("1828472645237297377", "4fkbdu8of"),
    ("1990000000000000000", "4tnrp481eua"),
])
def test_syndication_token_matches_javascript(pid, token):
    assert xpost.syndication_token(pid) == token


def test_parse_syndication(syndication_post):
    post = xpost.parse_syndication(syndication_post)
    assert post.id == "1850000000000000001"
    assert post.url == "https://x.com/examplelab/status/1850000000000000001"
    assert post.author_handle == "examplelab"
    # media link cut off by display_text_range, t.co link expanded
    assert post.text == "Our new paper on local LLMs is out: https://example.org/paper Thread"
    assert [m.kind for m in post.media] == ["photo", "video"]
    assert post.media[0].alt_text == "A chart"
    assert post.media[1].video_url == "https://video.twimg.com/high.mp4"
    assert post.media[1].duration_s == 95
    assert post.has_video
    assert post.quoted.author_handle == "someone"
    assert post.likes == 42


def test_post_roundtrip(syndication_post):
    post = xpost.parse_syndication(syndication_post)
    assert Post.from_dict(post.to_dict()) == post


def test_tombstone_is_unavailable():
    with pytest.raises(xpost.PostUnavailable):
        xpost.parse_syndication({"__typename": "TweetTombstone"})


def test_v1_dates_become_iso(syndication_post):
    syndication_post["created_at"] = "Wed Oct 30 08:15:00 +0000 2026"
    assert xpost.parse_syndication(syndication_post).created_at == "2026-10-30T08:15:00Z"


class FakeResponse:
    def __init__(self, status, data=None):
        self.status_code = status
        self._data = data
        self.content = b"{}" if data is not None else b""

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(self.status_code)


def test_fetch_post_not_found(monkeypatch):
    monkeypatch.setattr(xpost.requests, "get", lambda *a, **k: FakeResponse(404))
    with pytest.raises(xpost.PostNotFound):
        xpost.fetch_post("https://x.com/a/status/1")


def test_unavailable_without_cookies_does_not_try_ytdlp(monkeypatch):
    monkeypatch.setattr(xpost.requests, "get", lambda *a, **k: FakeResponse(200))
    monkeypatch.setattr(xpost, "_fetch_ytdlp", lambda pid: pytest.fail("needs cookies"))
    with pytest.raises(xpost.PostUnavailable):
        xpost.fetch_post("1")


def test_unavailable_with_cookies_falls_back_to_ytdlp(monkeypatch, syndication_post):
    monkeypatch.setenv("TWITTERMCP_COOKIES_BROWSER", "firefox")
    monkeypatch.setattr(xpost.requests, "get", lambda *a, **k: FakeResponse(200))
    monkeypatch.setattr(xpost, "_fetch_ytdlp", lambda pid: xpost.parse_syndication(syndication_post))
    assert xpost.fetch_post("1").author_handle == "examplelab"
