# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

"""Client for the local Gemma model via the Ollama API (http://localhost:11434).
No data leaves your machine.
"""
import base64
import os

import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("GEMMA_MODEL", "gemma4:e4b")
NUM_CTX = int(os.environ.get("GEMMA_NUM_CTX", "32768"))


def available() -> bool:
    try:
        requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        return True
    except requests.RequestException:
        return False


def chat(prompt: str, images: list[bytes] | None = None, json_schema: dict | None = None,
         timeout: int = 900) -> str:
    msg = {"role": "user", "content": prompt}
    if images:
        msg["images"] = [base64.b64encode(i).decode() for i in images]
    payload = {"model": MODEL, "messages": [msg], "stream": False,
               "options": {"temperature": 0.2, "num_ctx": NUM_CTX}}
    if json_schema:
        payload["format"] = json_schema
    r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()["message"]["content"]
