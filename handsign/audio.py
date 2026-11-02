"""Microphone capture.

One always-open 16 kHz mono input stream feeds two consumers:
  - Push-to-talk: call start_recording() when a gesture engages and
    stop_recording() when it releases; you get back the captured float32 audio.
  - Parallel mode: run_vad() runs an energy-based voice-activity segmenter in a
    background thread and calls `on_utterance(audio)` whenever a spoken segment
    completes (speech, then trailing silence).

16 kHz mono float32 is exactly what faster-whisper expects, so no resampling.
"""

from __future__ import annotations

import threading
from collections import deque

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
BLOCK = 1600  # 100 ms blocks


class AudioCapture:
    def __init__(self, device: int | None = None):
        self.device = device
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        self._recording = False
        self._rec_chunks: list[np.ndarray] = []
        # Small rolling buffer so VAD can include the pre-speech onset.
        self._ring: deque[np.ndarray] = deque(maxlen=5)
        self._latest_rms = 0.0
        self._vad_thread: threading.Thread | None = None
        self._vad_stop = threading.Event()

    # --------------------------------------------------------------- stream
    def _callback(self, indata, frames, time_info, status):  # noqa: ARG002
        mono = indata[:, 0].copy() if indata.ndim > 1 else indata.copy()
        self._latest_rms = float(np.sqrt(np.mean(mono**2)) + 1e-9)
        with self._lock:
            self._ring.append(mono)
            if self._recording:
                self._rec_chunks.append(mono)

    def start(self) -> None:
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32",
            blocksize=BLOCK, device=self.device, callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        self._vad_stop.set()
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    @property
    def rms(self) -> float:
        return self._latest_rms

    # ---------------------------------------------------------- push-to-talk
    def start_recording(self) -> None:
        with self._lock:
            # Seed with the ring buffer so we don't clip the first syllable.
            self._rec_chunks = list(self._ring)
            self._recording = True

    def stop_recording(self) -> np.ndarray:
        with self._lock:
            self._recording = False
            chunks = self._rec_chunks
            self._rec_chunks = []
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks).astype(np.float32)

    # ----------------------------------------------------------- parallel VAD
    def run_vad(
        self,
        on_utterance,
        energy_threshold: float = 0.012,
        silence_ms: int = 600,
        max_segment_s: float = 12.0,
        min_segment_ms: int = 250,
    ) -> None:
        """Start the energy-VAD segmenter thread."""
        self._vad_stop.clear()
        self._vad_thread = threading.Thread(
            target=self._vad_loop,
            args=(on_utterance, energy_threshold, silence_ms, max_segment_s, min_segment_ms),
            daemon=True,
        )
        self._vad_thread.start()

    def _vad_loop(self, on_utterance, energy_threshold, silence_ms, max_segment_s, min_segment_ms):
        block_ms = BLOCK / SAMPLE_RATE * 1000.0
        silence_blocks_needed = max(1, int(silence_ms / block_ms))
        max_blocks = int(max_segment_s * 1000 / block_ms)
        min_blocks = max(1, int(min_segment_ms / block_ms))

        in_speech = False
        seg: list[np.ndarray] = []
        silent_run = 0
        last_len = 0

        while not self._vad_stop.is_set():
            sd.sleep(int(block_ms))
            with self._lock:
                if not self._ring:
                    continue
                block = self._ring[-1]
                # Avoid double-counting if no new block arrived.
                if len(self._ring) == last_len and in_speech:
                    pass
                last_len = len(self._ring)
            rms = float(np.sqrt(np.mean(block**2)) + 1e-9)
            voiced = rms >= energy_threshold

            if voiced:
                if not in_speech:
                    in_speech = True
                    seg = []
                seg.append(block)
                silent_run = 0
                if len(seg) >= max_blocks:
                    self._emit(seg, min_blocks, on_utterance)
                    in_speech, seg, silent_run = False, [], 0
            elif in_speech:
                seg.append(block)
                silent_run += 1
                if silent_run >= silence_blocks_needed:
                    self._emit(seg, min_blocks, on_utterance)
                    in_speech, seg, silent_run = False, [], 0

    @staticmethod
    def _emit(seg, min_blocks, on_utterance):
        if len(seg) >= min_blocks:
            audio = np.concatenate(seg).astype(np.float32)
            on_utterance(audio)
