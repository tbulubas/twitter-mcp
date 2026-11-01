# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

"""The use cases with every slow or external step replaced by a fake."""

import json

import pytest

from twittermcp.core import analyze, db, gemma, media, pipeline, transcribe, xpost
from twittermcp.core.transcribe import Segment, Transcript

SUMMARY = {"summary": "A lab released a paper.", "key_points": ["paper is out"],
           "speakers": [{"speaker": "host", "statements": ["[00:05] We trained it on a laptop."]}],
           "topics": ["local LLMs"], "claims_to_verify": [], "answer": None}


@pytest.fixture
def fakes(monkeypatch, syndication_post, tmp_path):
    calls = {"fetch": 0, "whisper": 0, "chat": []}

    def fetch(pid):
        calls["fetch"] += 1
        return xpost.parse_syndication(syndication_post)

    def whisper(path):
        calls["whisper"] += 1
        return Transcript("en", 95.0, [Segment(5.0, 8.0, "We trained it on a laptop.")])

    def chat(prompt, images=None, json_schema=None, **kw):
        calls["chat"].append(prompt)
        return json.dumps(SUMMARY) if json_schema else "An image."

    video = tmp_path / "video-1.mp4"
    photo = tmp_path / "photo-1.jpg"
    monkeypatch.setattr(xpost, "fetch_post", fetch)
    monkeypatch.setattr(transcribe, "transcribe", whisper)
    monkeypatch.setattr(media, "download_videos", lambda post, dest: [video])
    monkeypatch.setattr(media, "download_photos", lambda post, dest: [photo])
    monkeypatch.setattr(media, "load_image", lambda path: b"jpeg")
    monkeypatch.setattr(media, "keyframes", lambda path: [b"f1", b"f2"])
    monkeypatch.setattr(gemma, "chat", chat)
    monkeypatch.setattr(gemma, "available", lambda: True)
    return calls


def test_get_post_is_cached(fakes):
    pipeline.get_post("https://x.com/examplelab/status/1850000000000000001")
    post = pipeline.get_post("1850000000000000001")
    assert fakes["fetch"] == 1
    assert post.media[1].video_url.endswith("high.mp4")
    pipeline.get_post("1850000000000000001", refresh=True)
    assert fakes["fetch"] == 2


def test_transcripts_are_cached(fakes):
    post = pipeline.get_post("1850000000000000001")
    first = pipeline.transcripts(post)
    again = pipeline.transcripts(post)
    assert fakes["whisper"] == 1
    assert first == again
    assert again[0].timestamped() == "[00:05] We trained it on a laptop."


def test_analyze_post(fakes):
    lines = []
    out = pipeline.analyze_post("1850000000000000001", language="sk", progress=lines.append)
    assert out["analysis"] == SUMMARY
    assert out["cached"] is False
    prompt = fakes["chat"][-1]
    assert "in Slovak" in prompt
    assert "[00:05] We trained it on a laptop." in prompt
    assert "Alt text by the author: A chart" in prompt
    assert "Quoted post by @someone" in prompt
    assert any("summarizing" in line for line in lines)

    calls = len(fakes["chat"])
    assert pipeline.analyze_post("1850000000000000001", language="sk")["cached"] is True
    assert len(fakes["chat"]) == calls
    # another language or question is a new analysis, but reuses transcript and image notes
    pipeline.analyze_post("1850000000000000001", question="Is the code public?")
    assert len(fakes["chat"]) == calls + 1
    assert "Is the code public?" in fakes["chat"][-1]
    assert fakes["whisper"] == 1


def test_analyze_needs_ollama(fakes, monkeypatch):
    monkeypatch.setattr(gemma, "available", lambda: False)
    with pytest.raises(pipeline.OllamaUnavailable):
        pipeline.analyze_post("1850000000000000001")


def test_recent_analyses(fakes):
    pipeline.analyze_post("1850000000000000001")
    [row] = db.recent_analyses()
    assert row["author_handle"] == "examplelab"
    assert row["summary"] == SUMMARY["summary"]


def test_long_transcript_is_condensed_in_chunks(monkeypatch):
    seen = []
    monkeypatch.setattr(gemma, "chat", lambda prompt, **kw: seen.append(prompt) or "notes")
    long = Transcript("en", 3600, [Segment(i, i + 1, "x" * 200) for i in range(200)])
    assert analyze.condense_transcript(long) == "\n".join(["notes"] * len(seen))
    assert len(seen) > 1
    assert all(len(p) < analyze.CHUNK_CHARS + 1000 for p in seen)


def test_short_transcript_is_used_verbatim():
    t = Transcript("en", 70, [Segment(3, 5, "Hello."), Segment(65, 68, "Bye.")])
    assert analyze.condense_transcript(t) == "[00:03] Hello.\n[01:05] Bye."
