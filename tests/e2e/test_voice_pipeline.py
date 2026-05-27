# tests/e2e/test_voice_pipeline.py
# Cenário: Pipeline de voz — VAD → STT → TTS com mocks

from __future__ import annotations

import pytest


class MockVAD:
    def __init__(self, speech_data: bytes | None = None):
        self._data = speech_data
        self._closed = False
        self._stream = None
        self.sample_rate = 16000
        self.is_capturing = False

    def open_stream(self):
        return self

    def read(self, size, exception_on_overflow=False):
        return b"\x00" * size

    def close(self):
        self._closed = True

    def is_speech(self, frame):
        return False

    async def record_until_silence(self, silence_threshold_ms=1500, max_duration_s=30, speech_start_frames=6):
        return self._data


class MockSTT:
    def __init__(self):
        self._loaded = False
        self.vram_usage_gb = 0.15

    async def ensure_loaded(self):
        self._loaded = True
        return True

    async def transcribe(self, audio_bytes, language="pt"):
        return "transcricao mock do audio"

    async def unload(self):
        self._loaded = False

    @property
    def is_loaded(self):
        return self._loaded


class MockTTS:
    async def synthesize(self, text):
        return b"audio_mock"


@pytest.mark.asyncio
async def test_voice_pipeline_listen_once():
    """Pipeline: listen_once transcreve áudio mock."""
    from lux.voice.pipeline import VoicePipeline
    from lux.voice.lifecycle import WhisperLifecycleManager

    stt = MockSTT()
    vad = MockVAD(b"\x01" * 8000)
    tts = MockTTS()
    lifecycle = WhisperLifecycleManager(stt)

    pipeline = VoicePipeline(vad=vad, stt=stt, tts=tts, lifecycle=lifecycle)
    result = await pipeline.listen_once()
    assert result is not None
    assert "transcricao" in result


@pytest.mark.asyncio
async def test_voice_pipeline_no_speech():
    """Pipeline: retorna None quando VAD não detecta fala."""
    from lux.voice.pipeline import VoicePipeline
    from lux.voice.lifecycle import WhisperLifecycleManager

    stt = MockSTT()
    vad = MockVAD(None)  # sem dados = sem fala
    tts = MockTTS()
    lifecycle = WhisperLifecycleManager(stt)

    pipeline = VoicePipeline(vad=vad, stt=stt, tts=tts, lifecycle=lifecycle)
    result = await pipeline.listen_once()
    assert result is None


@pytest.mark.asyncio
async def test_sentence_splitter():
    """SentenceSplitter: acumula tokens e emite frases completas."""
    from lux.voice.tts import SentenceSplitter

    splitter = SentenceSplitter()
    assert splitter.feed("Ola") is None
    assert splitter.feed(" mundo") is None
    sentence = splitter.feed(".")
    assert sentence == "Ola mundo."

    assert splitter.feed("Segunda") is None
    assert splitter.feed(" frase!") == "Segunda frase!"
    assert splitter.flush() is None


@pytest.mark.asyncio
async def test_sentence_splitter_overflow():
    """SentenceSplitter: flush forçado quando buffer > 4096."""
    from lux.voice.tts import SentenceSplitter

    splitter = SentenceSplitter()
    long_text = "a" * 4100
    result = splitter.feed(long_text)
    assert result is not None
    assert len(result) > 4000


@pytest.mark.asyncio
async def test_stt_lifecycle_refcount():
    """WhisperLifecycleManager: acquire/release atômico."""
    from lux.voice.lifecycle import WhisperLifecycleManager
    stt = MockSTT()
    mgr = WhisperLifecycleManager(stt)

    assert await mgr.acquire() is True
    assert stt.is_loaded is True
    assert WhisperLifecycleManager._refcount == 1

    assert await mgr.acquire() is True
    assert WhisperLifecycleManager._refcount == 2

    await mgr.release()
    assert WhisperLifecycleManager._refcount == 1

    await mgr.release()
    assert WhisperLifecycleManager._refcount == 0


@pytest.mark.asyncio
async def test_voice_pipeline_stop():
    """Pipeline: stop interrompe e descarrega STT."""
    from lux.voice.pipeline import VoicePipeline
    from lux.voice.lifecycle import WhisperLifecycleManager

    stt = MockSTT()
    pipeline = VoicePipeline(
        vad=MockVAD(), stt=stt, tts=MockTTS(),
        lifecycle=WhisperLifecycleManager(stt),
    )
    pipeline.stop()
    assert pipeline.state.name == "STOPPED"


@pytest.mark.asyncio
async def test_voice_pipeline_reset():
    """Pipeline: reset após stop volta ao estado IDLE."""
    from lux.voice.pipeline import VoicePipeline, VoicePipelineState
    from lux.voice.lifecycle import WhisperLifecycleManager

    pipeline = VoicePipeline(
        vad=MockVAD(), stt=MockSTT(), tts=MockTTS(),
        lifecycle=WhisperLifecycleManager(MockSTT()),
    )
    pipeline.stop()
    pipeline.reset()
    assert pipeline.state == VoicePipelineState.IDLE
