# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

"""Speech to text with faster-whisper, locally, on the GPU when it works.

The model is downloaded from Hugging Face on first use (large-v3-turbo is
about 1.6 GB) and cached there. If CUDA is not usable (missing cuBLAS/cuDNN
DLLs, see the `cuda` extra) it falls back to the CPU and logs why.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

MODEL = os.environ.get("WHISPER_MODEL", "large-v3-turbo")
DEVICE = os.environ.get("WHISPER_DEVICE", "cuda")

_model = None
_device: str | None = None


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class Transcript:
    language: str
    duration_s: float
    segments: list[Segment] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.segments)

    def timestamped(self) -> str:
        """One line per segment, `[mm:ss] text`, the form the LLM prompts use."""
        return "\n".join(f"[{_clock(s.start)}] {s.text}" for s in self.segments)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Transcript:
        return cls(d["language"], d["duration_s"], [Segment(**s) for s in d["segments"]])


def _clock(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _add_cuda_dll_dirs() -> None:
    """Put the DLLs of the pip packages nvidia-cublas-cu12 / nvidia-cudnn-cu12
    on the PATH, where CTranslate2 looks for them on Windows."""
    if sys.platform != "win32":
        return
    try:
        import nvidia
    except ImportError:
        return
    bins = [str(p) for root in nvidia.__path__ for p in Path(root).glob("*/bin") if p.is_dir()]
    os.environ["PATH"] = os.pathsep.join(bins + [os.environ.get("PATH", "")])


def _load(device: str):
    global _model, _device
    from faster_whisper import WhisperModel

    if device == "cuda":
        _add_cuda_dll_dirs()
    _model = WhisperModel(MODEL, device=device, compute_type="float16" if device == "cuda" else "int8")
    _device = device
    return _model


def transcribe(audio: Path) -> Transcript:
    """Transcribe any audio or video file PyAV can read (mp4 included)."""
    try:
        return _run(_model if _model is not None else _load(DEVICE), audio)
    except (RuntimeError, OSError) as e:
        if DEVICE == "cpu" or _device == "cpu":
            raise
        # CUDA libraries are often only found when the first segment is decoded
        log.warning("whisper on %s failed (%s), falling back to the CPU", DEVICE, e)
        return _run(_load("cpu"), audio)


def _run(model, audio: Path) -> Transcript:
    segments, info = model.transcribe(str(audio), vad_filter=True, beam_size=5)
    return Transcript(
        language=info.language,
        duration_s=round(info.duration, 2),
        segments=[Segment(round(s.start, 2), round(s.end, 2), s.text.strip()) for s in segments],
    )
