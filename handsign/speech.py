"""Speech-to-text via faster-whisper, plus a background transcription service.

Transcription is too slow to run inline in the camera loop, so jobs are queued
and processed on a worker thread. Each job carries the captured audio plus a
context dict (which fusion mode produced it, the gesture held at the time);
when transcription finishes, the service hands (text, context) to a routing
callback the engine supplies.

The model is local (no network at inference time) — once downloaded it lives in
the HuggingFace cache. Default "base.en" balances speed and accuracy on CPU.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field

import numpy as np
from faster_whisper import WhisperModel

from .audio import SAMPLE_RATE


@dataclass
class Job:
    audio: np.ndarray
    context: dict = field(default_factory=dict)


class Transcriber:
    def __init__(self, model: str = "base.en", device: str = "auto",
                 compute_type: str = "int8"):
        self.model = WhisperModel(model, device=device, compute_type=compute_type)

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size < SAMPLE_RATE // 10:  # <100 ms, nothing useful
            return ""
        segments, _ = self.model.transcribe(
            audio, language="en", beam_size=1, vad_filter=True,
        )
        return " ".join(s.text.strip() for s in segments).strip()


class TranscriptionService:
    """Owns a Transcriber on a worker thread. submit(job) -> async route."""

    def __init__(self, transcriber: Transcriber, on_result):
        self._t = transcriber
        self._on_result = on_result        # callable(text: str, context: dict)
        self._q: "queue.Queue[Job | None]" = queue.Queue()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._busy = False

    def start(self) -> None:
        self._thread.start()

    def submit(self, audio: np.ndarray, context: dict) -> None:
        self._q.put(Job(audio=audio, context=context))

    @property
    def busy(self) -> bool:
        return self._busy or not self._q.empty()

    def _loop(self) -> None:
        while True:
            job = self._q.get()
            if job is None:
                break
            self._busy = True
            try:
                text = self._t.transcribe(job.audio)
                if text:
                    self._on_result(text, job.context)
            except Exception as e:  # keep the worker alive on a bad segment
                print(f"[transcribe error] {e}")
            finally:
                self._busy = False

    def stop(self) -> None:
        self._q.put(None)
