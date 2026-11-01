# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

"""The use cases every interface calls: get, transcribe and analyze a post.

Each step is cached in the database, so a repeated call only does the work
that is still missing. `progress` receives short English status lines for
long runs (MCP log messages, CLI output).
"""

from __future__ import annotations

from collections.abc import Callable

from twittermcp.core import analyze, config, db, gemma, media, transcribe, xpost
from twittermcp.core.transcribe import Transcript
from twittermcp.core.xpost import Post

Progress = Callable[[str], None]


class OllamaUnavailable(Exception):
    code = "ollama_unavailable"


def _quiet(_: str) -> None:
    pass


def get_post(url_or_id: str, refresh: bool = False) -> Post:
    pid = xpost.post_id(url_or_id)
    if not refresh and (cached := db.get_post(pid)):
        return Post.from_dict(cached)
    post = xpost.fetch_post(pid)
    db.save_post(post.to_dict())
    return post


def transcripts(post: Post, progress: Progress = _quiet) -> list[Transcript]:
    """One transcript per video of the post, in order."""
    model = transcribe.MODEL
    videos = [m for m in post.media if m.kind in ("video", "animated_gif")]
    found: dict[int, Transcript] = {}
    for i in range(len(videos)):
        if cached := db.get_transcript(post.id, i, model):
            found[i] = Transcript.from_dict(cached)
    if len(found) == len(videos):
        return [found[i] for i in range(len(videos))]

    progress(f"downloading {len(videos)} video(s)")
    files = media.download_videos(post, config.media_dir(post.id))
    for i, path in enumerate(files):
        if i in found:
            continue
        if videos[i].kind == "animated_gif":  # X's GIFs have no sound
            t = Transcript(language="", duration_s=videos[i].duration_s or 0.0)
        else:
            progress(f"transcribing video {i + 1}/{len(files)} with whisper {model}")
            t = transcribe.transcribe(path)
        db.save_transcript(post.id, i, model, t.to_dict())
        found[i] = t
    return [found[i] for i in sorted(found)]


def image_notes(post: Post, progress: Progress = _quiet) -> list[str]:
    """Descriptions of the photos and of each video's frames, in media order."""
    notes = []
    dest = config.media_dir(post.id)
    counts = {"photo": 0, "video": 0}
    for i, m in enumerate(post.media):
        group = "photo" if m.kind == "photo" else "video"
        n = counts[group]
        counts[group] += 1
        key = f"{i}:{m.kind}"
        if cached := db.get_image_note(post.id, key, gemma.MODEL):
            notes.append(cached)
            continue
        # downloads skip files that are already there
        if group == "photo":
            progress(f"describing image {i + 1}")
            note = analyze.describe_image(media.load_image(media.download_photos(post, dest)[n]), post)
        else:
            progress(f"describing frames of video {i + 1}")
            note = analyze.describe_frames(media.keyframes(media.download_videos(post, dest)[n]), post)
        if m.alt_text:
            note = f"{note} (Alt text by the author: {m.alt_text})"
        db.save_image_note(post.id, key, gemma.MODEL, note)
        notes.append(note)
    return notes


def analyze_post(url_or_id: str, question: str | None = None, language: str = "en",
                 refresh: bool = False, progress: Progress = _quiet) -> dict:
    """Summary, key points and who-said-what of a post, with its videos and images."""
    post = get_post(url_or_id, refresh=refresh)
    q = (question or "").strip()
    if not refresh and (cached := db.get_analysis(post.id, q, language, gemma.MODEL)):
        return {"post": post.to_dict(), "analysis": cached, "cached": True}
    if not gemma.available():
        raise OllamaUnavailable(gemma.OLLAMA_URL)

    texts = [analyze.condense_transcript(t) for t in transcripts(post, progress) if t.segments]
    notes = image_notes(post, progress)
    progress(f"summarizing with {gemma.MODEL}")
    result = analyze.summarize(post, texts, notes, question=q or None, language=language)
    db.save_analysis(post.id, q, language, gemma.MODEL, result)
    return {"post": post.to_dict(), "analysis": result, "cached": False}
