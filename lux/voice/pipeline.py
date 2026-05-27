# lux/voice/pipeline.py
# Módulo: Voice
# Dependências: voice/vad.py, voice/stt.py, voice/tts.py, voice/lifecycle.py
# Status: IMPLEMENTADO
# Notas: Pipeline completo de voz: VAD → STT → LLM → TTS.
#   Modos: push-to-talk (padrão), wake-word, always-on (desabilitado).

from __future__ import annotations

import asyncio
import logging
from enum import Enum, auto
from typing import AsyncGenerator, Optional

from lux.agent.state import UserProfile
from lux.voice.interactive import InteractiveListener, VoiceMode
from lux.voice.lifecycle import WhisperLifecycleManager
from lux.voice.stt import STTEngine
from lux.voice.tts import SentenceSplitter, TTSEngine
from lux.voice.vad import VADDetector
from lux.voice.wake_word import WakeWordDetector
from lux.voice.classifier import IntentClassifier
from lux.voice.omni_engine import OmniEngine

logger = logging.getLogger(__name__)


class VoicePipeline:
    """Pipeline completo de voz. Suporta MiniCPM-o 4.5 unificado."""

    def __init__(
        self,
        vad: Optional[VADDetector] = None,
        stt: Optional[STTEngine] = None,
        tts: Optional[TTSEngine] = None,
        lifecycle: Optional[WhisperLifecycleManager] = None,
        wake: Optional[WakeWordDetector] = None,
        classifier: Optional[IntentClassifier] = None,
        omni: Optional[OmniEngine] = None,
    ):
        self._vad = vad or VADDetector()
        self._stt = stt or STTEngine()
        self._tts = tts or TTSEngine()
        self._lifecycle = lifecycle or WhisperLifecycleManager(self._stt)
        self._wake = wake or WakeWordDetector.get_instance()
        self._classifier = classifier or IntentClassifier()
        self._omni = omni
        self._mode = VoiceMode.OFF
        self._interactive: Optional[InteractiveListener] = None
        self._state = VoicePipelineState.IDLE
        self._stop_event = asyncio.Event()
        self._is_speaking = False

    @property
    def mode(self) -> VoiceMode:
        return self._mode

    @mode.setter
    def mode(self, value: VoiceMode):
        self._mode = value

    @property
    def state(self) -> VoicePipelineState:
        return self._state

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking

    async def listen_once(self) -> Optional[str]:
        """
        Uma rodada completa de escuta (push-to-talk).
        Retorna texto transcrito ou None se nada detectado.
        """
        self._state = VoicePipelineState.LISTENING
        self._stop_event.clear()

        try:
            if not await self._lifecycle.acquire():
                logger.warning("STT indisponivel — pulando voz")
                return None

            audio = await self._vad.record_until_silence()
            if audio is None:
                return None

            self._state = VoicePipelineState.PROCESSING
            text = await self._stt.transcribe(audio)
            return text

        finally:
            await self._lifecycle.release()
            self._state = VoicePipelineState.IDLE

    async def speak_streaming(
        self,
        text_generator: AsyncGenerator[str, None],
    ):
        """
        Streaming TTS: começa a falar antes do LLM terminar.
        Acumula tokens, emite frases via Piper.
        """
        self._state = VoicePipelineState.SPEAKING
        self._is_speaking = True
        splitter = SentenceSplitter()

        try:
            async for token in text_generator:
                if self._stop_event.is_set():
                    break
                sentence = splitter.feed(token)
                if sentence:
                    await self._speak_sentence(sentence)
                    if self._stop_event.is_set():
                        break

            remaining = splitter.flush()
            if remaining and not self._stop_event.is_set():
                await self._speak_sentence(remaining)

        finally:
            self._is_speaking = False
            self._state = VoicePipelineState.IDLE

    async def _speak_sentence(self, text: str):
        audio = await self._tts.synthesize(text)
        if audio:
            try:
                import pyaudio
                p = pyaudio.PyAudio()
                stream = p.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=22050,
                    output=True,
                )
                stream.write(audio)
                stream.stop_stream()
                stream.close()
                p.terminate()
            except Exception as e:
                logger.debug("Falha ao reproduzir audio: %s", e)

    def stop(self):
        """Interrompe fala imediatamente e descarrega STT."""
        self._stop_event.set()
        self._state = VoicePipelineState.STOPPED
        asyncio.create_task(self._lifecycle.force_unload())

    def reset(self):
        """Reseta para estado IDLE após stop."""
        self._stop_event.clear()
        self._state = VoicePipelineState.IDLE

    async def shutdown(self):
        """Desliga pipeline completamente."""
        self.stop()
        self._vad.close()
        await self._lifecycle.force_unload()

    async def load_stt(self) -> bool:
        return await self._lifecycle.acquire()

    async def unload_stt(self):
        await self._lifecycle.release()


class ListeningMode(Enum):
    OFF = auto()
    PUSH_TO_TALK = auto()
    WAKE_WORD = auto()
    ALWAYS_ON = auto()


class VoicePipelineState(Enum):
    IDLE = auto()
    LISTENING = auto()
    PROCESSING = auto()
    SPEAKING = auto()
    STOPPED = auto()
