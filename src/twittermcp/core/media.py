# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

"""Download a post's photos and videos and sample frames from the videos.

Photos come straight from pbs.twimg.com, videos through yt-dlp (which picks
X's progressive mp4, so no ffmpeg is needed). Frames are decoded with PyAV.
"""

from __future__ import annotations

import io
from pathlib import Path

import requests

from twittermcp.core import config
from twittermcp.core.xpost import USER_AGENT, Post

# longest side of images sent to the vision model
MAX_IMAGE_SIDE = 1024


def download_photos(post: Post, dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, m in enumerate(p for p in post.media if p.kind == "photo"):
        path = dest / f"photo-{i + 1}{Path(m.url).suffix or '.jpg'}"
        if not path.exists():
            r = requests.get(m.url, params={"name": "large"}, headers={"User-Agent": USER_AGENT}, timeout=60)
            r.raise_for_status()
            path.write_bytes(r.content)
        paths.append(path)
    return paths


def download_videos(post: Post, dest: Path) -> list[Path]:
    """All videos and GIFs of the post, in order, as video-1.mp4, video-2.mp4, ..."""
    if not post.has_video:
        return []
    dest.mkdir(parents=True, exist_ok=True)
    existing = sorted(dest.glob("video-*.mp4"))
    if existing:
        return existing

    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "format": "best[ext=mp4]/best",
        "outtmpl": str(dest / "video-%(autonumber)d.%(ext)s"),
        **config.cookie_options(),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([f"https://x.com/i/status/{post.id}"])
    return sorted(dest.glob("video-*.mp4"))


def keyframes(video: Path, count: int = 6) -> list[bytes]:
    """`count` JPEG frames spread evenly over the video, scaled for the vision model."""
    import av

    frames: list[bytes] = []
    with av.open(str(video)) as container:
        stream = container.streams.video[0]
        duration = float(container.duration / av.time_base) if container.duration else 0.0
        if duration <= 0:
            return frames
        for k in range(count):
            # the middle of each of `count` equal slices: skips black first frames
            t = duration * (k + 0.5) / count
            container.seek(int(t / stream.time_base), stream=stream)
            frame = next(container.decode(stream), None)
            if frame is not None:
                frames.append(to_jpeg(frame.to_image()))
    return frames


def load_image(path: Path) -> bytes:
    from PIL import Image

    with Image.open(path) as img:
        return to_jpeg(img)


def to_jpeg(img) -> bytes:
    img = img.convert("RGB")
    img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()
