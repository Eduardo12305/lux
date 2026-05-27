# lux/voice/vad.py
# Módulo: Voice
# Dependências: webrtcvad (leve, CPU, ~1ms por frame)
# Status: IMPLEMENTADO
# Notas: Detecta início/fim de fala. webrtcvad modo 3 (mais agressivo).

from __future__ import annotations

import logging
import time
from typing import Optional

import pyaudio
import webrtcvad

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
FRAME_DURATION_MS = 30
FRAME_SIZE = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)
SILENCE_THRESHOLD_MS = 1500
SPEECH_START_FRAMES = 6
MAX_RECORDING_SECONDS = 30
VAD_MODE = 3


class VADDetector:
    """Voice Activity Detection usando webrtcvad."""

    def __init__(self, sample_rate: int = SAMPLE_RATE, mode: int = VAD_MODE):
        self._sample_rate = sample_rate
        self._vad = webrtcvad.Vad(mode)
        self._audio = pyaudio.PyAudio()
        self._stream: Optional[pyaudio.Stream] = None
        self._is_capturing = False

    def open_stream(self) -> pyaudio.Stream:
        self._stream = self._audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self._sample_rate,
            input=True,
            frames_per_buffer=FRAME_SIZE,
        )
        return self._stream

    def close(self):
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        self._audio.terminate()

    def is_speech(self, frame: bytes) -> bool:
        return self._vad.is_speech(frame, self._sample_rate)

    async def record_until_silence(
        self,
        silence_threshold_ms: int = SILENCE_THRESHOLD_MS,
        max_duration_s: int = MAX_RECORDING_SECONDS,
        speech_start_frames: int = SPEECH_START_FRAMES,
    ) -> Optional[bytes]:
        """
        Grava até detectar silencio prolongado (assíncrono, roda em thread pool).
        Retorna bytes de audio PCM 16-bit mono 16kHz.
        """
        import asyncio
        return await asyncio.to_thread(
            self._record_until_silence_sync,
            silence_threshold_ms,
            max_duration_s,
            speech_start_frames,
        )

    def _record_until_silence_sync(
        self,
        silence_threshold_ms: int,
        max_duration_s: int,
        speech_start_frames: int,
    ) -> Optional[bytes]:
        stream = self._stream or self.open_stream()

        frames: list[bytes] = []
        speech_frames = 0
        silence_frames = 0
        is_speaking = False
        silence_frame_limit = int(silence_threshold_ms / FRAME_DURATION_MS)
        max_frames = int(max_duration_s * 1000 / FRAME_DURATION_MS)

        logger.debug("VAD: ouvindo...")

        for _ in range(max_frames):
            frame = stream.read(FRAME_SIZE, exception_on_overflow=False)
            has_speech = self._vad.is_speech(frame, self._sample_rate)

            if has_speech:
                speech_frames += 1
                silence_frames = 0
                if not is_speaking and speech_frames >= speech_start_frames:
                    is_speaking = True
                    logger.debug("VAD: fala detectada")
                    frames.extend([b"\x00\x00"] * (speech_start_frames * FRAME_SIZE))
            else:
                silence_frames += 1
                speech_frames = 0

            if is_speaking:
                frames.append(frame)
                if silence_frames >= silence_frame_limit:
                    logger.debug("VAD: silencio — parando gravacao (%d frames)", len(frames))
                    break

        if frames and is_speaking:
            return b"".join(frames)
        return None

    @property
    def is_capturing(self) -> bool:
        return self._is_capturing

    @property
    def sample_rate(self) -> int:
        return self._sample_rate
