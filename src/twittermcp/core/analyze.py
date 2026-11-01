# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

"""LLM steps: describe images and video frames, summarize a post with its transcript.

Gemma only reads and writes text here. What the post *is* (author, date,
media, transcript timestamps) comes from code and is never asked of the model.
"""

from __future__ import annotations

import json

from twittermcp.core import gemma
from twittermcp.core.transcribe import Transcript
from twittermcp.core.xpost import Post

# transcripts longer than this are summarized chunk by chunk first
CHUNK_CHARS = 12_000

LANGUAGES = {"en": "English", "sk": "Slovak", "de": "German", "cs": "Czech", "uk": "Ukrainian"}

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "3-6 sentences"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "speakers": {
            "type": "array",
            "description": "who says what in the video; empty without a transcript",
            "items": {
                "type": "object",
                "properties": {
                    "speaker": {"type": "string",
                                "description": "name if stated, else a description like 'host', 'guest 1'"},
                    "statements": {"type": "array", "items": {"type": "string"},
                                   "description": "main statements, each with its [mm:ss] timestamp"},
                },
                "required": ["speaker", "statements"],
            },
        },
        "topics": {"type": "array", "items": {"type": "string"}},
        "claims_to_verify": {"type": "array", "items": {"type": "string"},
                             "description": "factual claims a reader should check"},
        "answer": {"type": ["string", "null"], "description": "answer to the user's question, if one was asked"},
    },
    "required": ["summary", "key_points", "speakers", "topics", "claims_to_verify", "answer"],
}


def language_name(code: str) -> str:
    return LANGUAGES.get(code, code)


def describe_image(image: bytes, post: Post) -> str:
    prompt = (
        "Describe this image from a post on X.com in 2-4 sentences. Transcribe any visible text "
        "(captions, charts, screenshots of other posts) word for word. Do not guess who people are "
        "unless their name is visible.\n\n"
        f"Post text: {post.text}"
    )
    return gemma.chat(prompt, images=[image]).strip()


def describe_frames(frames: list[bytes], post: Post) -> str:
    prompt = (
        "These are frames sampled evenly from a video in a post on X.com, in order. Describe in "
        "3-5 sentences what the video shows: setting, people, on-screen text, slides or charts. "
        "Do not guess who people are unless their name is visible.\n\n"
        f"Post text: {post.text}"
    )
    return gemma.chat(prompt, images=frames).strip()


def condense_transcript(transcript: Transcript) -> str:
    """The transcript as it goes into the summary prompt: verbatim when it fits,
    otherwise chunk notes that keep the timestamps and who said what."""
    full = transcript.timestamped()
    if len(full) <= CHUNK_CHARS:
        return full
    notes = []
    for chunk in _chunks(full.splitlines(), CHUNK_CHARS):
        prompt = (
            "This is part of a timestamped video transcript. Write compact notes of everything said: "
            "one line per statement, starting with its [mm:ss] timestamp and, where it can be told "
            "from the text, who is speaking. Keep numbers, names and claims exact.\n\n" + chunk
        )
        notes.append(gemma.chat(prompt).strip())
    return "\n".join(notes)


def _chunks(lines: list[str], size: int) -> list[str]:
    chunks, current, length = [], [], 0
    for line in lines:
        if current and length + len(line) > size:
            chunks.append("\n".join(current))
            current, length = [], 0
        current.append(line)
        length += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


def summarize(post: Post, transcripts: list[str], image_notes: list[str],
              question: str | None = None, language: str = "en") -> dict:
    parts = [f"Author: {post.author_name} (@{post.author_handle})", f"Date: {post.created_at}",
             f"Post text:\n{post.text}"]
    if post.quoted:
        parts.append(f"Quoted post by @{post.quoted.author_handle}:\n{post.quoted.text}")
    for i, note in enumerate(image_notes, 1):
        parts.append(f"Visual {i}: {note}")
    for i, t in enumerate(transcripts, 1):
        parts.append(f"Video {i} transcript:\n{t}")

    prompt = (
        f"Analyze this post from X.com. Write all output in {language_name(language)}. "
        "Base everything only on the material below; if something is unclear, say so instead of "
        "guessing. In 'speakers', attribute statements only as far as the transcript supports it."
    )
    if question:
        prompt += f" Also answer the user's question in 'answer': {question}"
    else:
        prompt += " Set 'answer' to null."
    prompt += "\n\n" + "\n\n".join(parts)
    return json.loads(gemma.chat(prompt, json_schema=SUMMARY_SCHEMA))
