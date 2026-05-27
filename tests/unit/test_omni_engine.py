# tests/unit/test_omni_engine.py
# Módulo: Testes de OmniEngine (MiniCPM-o 4.5)
# Status: IMPLEMENTADO

from __future__ import annotations

import pytest
import numpy as np
from unittest.mock import patch

from lux.voice.omni_engine import OmniEngine, SAMPLE_RATE_IN, SAMPLE_RATE_OUT, GPU_ENV


def test_omni_engine_init():
    with patch("lux.voice.omni_engine.get_config", return_value=type("c", (), {"omni_model_path": "/tmp/test.gguf"})()):
        engine = OmniEngine(model_path="/tmp/test.gguf", binary_path="llama-omni-cli")
    assert engine.is_ready is False
    assert engine.uptime_seconds == 0.0


def test_omni_engine_not_ready_before_start():
    with patch("lux.voice.omni_engine.get_config", return_value=type("c", (), {"omni_model_path": ""})()):
        engine = OmniEngine(model_path="/tmp/test.gguf")
    assert engine.is_ready is False


def test_omni_engine_stop_before_start():
    with patch("lux.voice.omni_engine.get_config", return_value=type("c", (), {"omni_model_path": ""})()):
        engine = OmniEngine(model_path="/tmp/test.gguf")
    import asyncio
    asyncio.run(engine.stop())
    assert engine.is_ready is False
    assert engine.uptime_seconds == 0.0


def test_omni_engine_not_ready_before_start():
    engine = OmniEngine()
    assert engine.is_ready is False
    with pytest.raises(RuntimeError):
        import asyncio
        asyncio.run(engine.send_audio_chunk(np.zeros(16000, dtype=np.float32)))


def test_omni_engine_stop_before_start():
    engine = OmniEngine()
    # não deve lançar exceção
    import asyncio
    asyncio.run(engine.stop())
    assert engine.is_ready is False


def test_gpu_env_vars():
    assert "HSA_OVERRIDE_GFX_VERSION" in GPU_ENV
    assert GPU_ENV["HSA_OVERRIDE_GFX_VERSION"] == "12.0.1"
    assert GPU_ENV["ROCR_VISIBLE_DEVICES"] == "0"


def test_omni_sample_rates():
    assert SAMPLE_RATE_IN == 16000
    assert SAMPLE_RATE_OUT == 22050


@pytest.mark.asyncio
async def test_omni_engine_stream_empty():
    """Stream de engine não iniciada retorna vazio."""
    engine = OmniEngine()
    engine._proc = type("MockProc", (), {"returncode": 0})()
    results = []
    async for token, audio in engine.stream_response():
        results.append(token)
    assert len(results) == 0


def test_omni_engine_with_custom_gfx():
    engine = OmniEngine(gfx_override="12.0.1")
    assert engine._gfx == "12.0.1"


def test_omni_engine_with_ref_audio():
    engine = OmniEngine(ref_audio_path="/tmp/ref.wav")
    assert engine._ref_audio == "/tmp/ref.wav"
