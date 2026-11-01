# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

"""Fetch a single X.com post and normalize it into a `Post`.

Public posts come from the syndication endpoint that X's own embeds use: no
login, no API key, one request per post. Posts it does not serve (protected
accounts, age-restricted content) fall back to yt-dlp with the user's cookies
when they are configured (see `config.cookie_options`).

This module is for user-triggered lookups of single posts, not for crawling
timelines: bulk scraping breaks X's terms and puts the account at risk.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

import requests

from twittermcp.core import config

SYNDICATION_URL = "https://cdn.syndication.twimg.com/tweet-result"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"

POST_URL = re.compile(
    r"(?:https?://)?(?:www\.|mobile\.)?"
    r"(?:x|twitter|fixupx|fxtwitter|vxtwitter|fixvx)\.com/"
    r"(?:[A-Za-z0-9_]+|i(?:/web)?)/status(?:es)?/(\d+)",
    re.IGNORECASE,
)


class PostError(Exception):
    """Base class; `code` is a stable identifier for callers (MCP clients, UI)."""

    code = "post_error"


class InvalidPostUrl(PostError):
    code = "invalid_url"


class PostNotFound(PostError):
    code = "not_found"


class PostUnavailable(PostError):
    """The post exists but is not served without login (protected, age-restricted, removed)."""

    code = "unavailable"


@dataclass
class Media:
    kind: str                      # photo | video | animated_gif
    url: str                       # the image itself, or the video's poster frame
    video_url: str | None = None   # best mp4 variant
    duration_s: float | None = None
    alt_text: str | None = None


@dataclass
class Post:
    id: str
    url: str
    author_name: str
    author_handle: str
    created_at: str                # ISO 8601, UTC
    text: str
    lang: str | None = None
    media: list[Media] = field(default_factory=list)
    quoted: Post | None = None
    likes: int | None = None
    replies: int | None = None

    @property
    def has_video(self) -> bool:
        return any(m.kind in ("video", "animated_gif") for m in self.media)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Post:
        d = dict(d)
        d["media"] = [Media(**m) for m in d.get("media", [])]
        if d.get("quoted"):
            d["quoted"] = cls.from_dict(d["quoted"])
        return cls(**d)


def post_id(url_or_id: str) -> str:
    """The numeric post id from a post URL (x.com, twitter.com, mirrors) or a bare id."""
    s = url_or_id.strip()
    if s.isdigit():
        return s
    if m := POST_URL.search(s):
        return m.group(1)
    raise InvalidPostUrl(s)


def syndication_token(pid: str) -> str:
    """The token the embed endpoint expects: JS `((id / 1e15) * Math.PI).toString(36)`
    with all zeros and the dot removed."""
    return re.sub(r"0+|\.", "", _js_radix(int(pid) / 1e15 * math.pi, 36))


def _js_radix(value: float, radix: int) -> str:
    """Port of V8's DoubleToRadixCString for a positive double: the shortest
    digit string that still reads back as `value`, rounded the same way."""
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    integer = math.floor(value)
    fraction = value - integer
    delta = max(0.5 * (math.nextafter(value, math.inf) - value), math.nextafter(0.0, 1.0))
    digits: list[int] = []
    if fraction >= delta:
        while True:
            fraction *= radix
            delta *= radix
            digit = int(fraction)
            digits.append(digit)
            fraction -= digit
            if fraction > 0.5 or (fraction == 0.5 and digit & 1):
                if fraction + delta > 1:
                    # round up; carries drop trailing digits that overflow
                    while True:
                        if not digits:
                            integer += 1
                            break
                        last = digits.pop()
                        if last + 1 < radix:
                            digits.append(last + 1)
                            break
                    break
            if fraction < delta:
                break
    head = ""
    n = int(integer)
    while True:
        n, r = divmod(n, radix)
        head = chars[r] + head
        if n == 0:
            break
    return head + ("." + "".join(chars[d] for d in digits) if digits else "")


def fetch_post(url_or_id: str) -> Post:
    pid = post_id(url_or_id)
    try:
        return _fetch_syndication(pid)
    except PostUnavailable:
        if not config.cookie_options():
            raise
        return _fetch_ytdlp(pid)


def _fetch_syndication(pid: str) -> Post:
    r = requests.get(
        SYNDICATION_URL,
        params={"id": pid, "token": syndication_token(pid), "lang": "en"},
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    if r.status_code == 404:
        raise PostNotFound(pid)
    r.raise_for_status()
    if not r.content.strip():
        raise PostUnavailable(pid)
    return parse_syndication(r.json())


def parse_syndication(data: dict) -> Post:
    """Normalize the syndication JSON of a post (and its quoted post)."""
    if data.get("__typename") == "TweetTombstone" or "id_str" not in data:
        raise PostUnavailable(data.get("id_str", ""))
    user = data.get("user") or {}
    handle = user.get("screen_name", "")
    return Post(
        id=data["id_str"],
        url=f"https://x.com/{handle or 'i'}/status/{data['id_str']}",
        author_name=user.get("name", ""),
        author_handle=handle,
        created_at=_iso(data.get("created_at", "")),
        text=_display_text(data),
        lang=data.get("lang"),
        media=[_media(m) for m in data.get("mediaDetails") or []],
        quoted=parse_syndication(data["quoted_tweet"]) if data.get("quoted_tweet") else None,
        likes=data.get("favorite_count"),
        replies=data.get("conversation_count"),
    )


def _display_text(data: dict) -> str:
    """The visible text: media links cut off, t.co links expanded."""
    text = data.get("text", "")
    if rng := data.get("display_text_range"):
        text = text[rng[0]:rng[1]]
    for u in (data.get("entities") or {}).get("urls") or []:
        if u.get("url") and u.get("expanded_url"):
            text = text.replace(u["url"], u["expanded_url"])
    return text.strip()


def _media(m: dict) -> Media:
    kind = m.get("type", "photo")
    media = Media(kind=kind, url=m.get("media_url_https", ""), alt_text=m.get("ext_alt_text"))
    if info := m.get("video_info"):
        mp4 = [v for v in info.get("variants") or [] if v.get("content_type") == "video/mp4"]
        if mp4:
            media.video_url = max(mp4, key=lambda v: v.get("bitrate") or 0)["url"]
        if ms := info.get("duration_millis"):
            media.duration_s = ms / 1000
    return media


def _iso(created_at: str) -> str:
    """Syndication dates are ISO already; v1.1-style dates are converted."""
    if not created_at or "T" in created_at:
        return created_at
    try:
        dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
    except ValueError:
        return created_at
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _fetch_ytdlp(pid: str) -> Post:
    """Fallback for posts that need a login: yt-dlp with the user's cookies.
    yt-dlp only covers posts with video; its info has the text and the author."""
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "skip_download": True, **config.cookie_options()}
    url = f"https://x.com/i/status/{pid}"
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        raise PostUnavailable(pid) from e
    entries = info.get("entries") or [info]
    first = entries[0]
    ts = first.get("timestamp")
    return Post(
        id=pid,
        url=f"https://x.com/{first.get('uploader_id') or 'i'}/status/{pid}",
        author_name=first.get("uploader", ""),
        author_handle=first.get("uploader_id", ""),
        created_at=datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z") if ts else "",
        text=first.get("description", ""),
        media=[Media(kind="video", url=e.get("thumbnail", ""), duration_s=e.get("duration"))
               for e in entries],
        likes=first.get("like_count"),
        replies=first.get("comment_count"),
    )
