# tests/unit/test_conversation_mode.py
# Módulo: Testes de ConversationMode + EmotionalContext + VoiceTones
# Status: IMPLEMENTADO

from __future__ import annotations

import time
import pytest
import numpy as np

from lux.voice.conversation_mode import ConversationModeManager
from lux.voice.emotional_context import (
    EmotionalContextDetector,
    EmotionalState,
    ADJUSTMENTS,
)
from lux.voice.tones import VoiceTones, SAMPLE_RATE


# ── ConversationModeManager ──────────────────────────────────────────────


def test_conversation_active_in_window():
    cm = ConversationModeManager()
    cm.activate()
    assert cm.is_active is True


def test_conversation_inactive_after_timeout():
    cm = ConversationModeManager()
    cm.CONVERSATION_WINDOW_S = 0.01
    cm.activate()
    time.sleep(0.02)
    assert cm.is_active is False


def test_activate_sets_flag():
    cm = ConversationModeManager()
    assert cm.is_active is False
    cm.activate()
    assert cm.is_active is True


def test_update_renews_timer():
    cm = ConversationModeManager()
    cm.CONVERSATION_WINDOW_S = 0.02
    cm.activate()
    time.sleep(0.015)
    cm.update("teste")
    time.sleep(0.015)
    assert cm.is_active is True


def test_topic_change_detected():
    cm = ConversationModeManager()
    assert cm.is_topic_change("mudando de assunto, quero falar de Python") is True
    assert cm.is_topic_change("outra coisa, voce pode me ajudar") is True
    assert cm.is_topic_change("alias, esquece isso") is True


def test_topic_change_normal():
    cm = ConversationModeManager()
    assert cm.is_topic_change("qual o status do build?") is False
    assert cm.is_topic_change("me lembra de comprar pao") is False


def test_deactivate_clears_context():
    cm = ConversationModeManager()
    cm.activate()
    cm.update("frase 1")
    cm.update("frase 2")
    cm.deactivate()
    assert cm.is_active is False
    assert len(cm.context) == 0


# ── EmotionalContextDetector ─────────────────────────────────────────────


def test_emotional_urgent():
    detector = EmotionalContextDetector()
    state = asyncio.run(detector.detect("Isso e urgente, preciso para agora"))
    assert state.state == "urgente"


def test_emotional_frustrated():
    detector = EmotionalContextDetector()
    state = asyncio.run(detector.detect("Isso nao funcionou de novo, toda vez a mesma coisa"))
    assert state.state == "frustrado"


def test_emotional_neutral():
    detector = EmotionalContextDetector()
    state = asyncio.run(detector.detect("qual o status do build?"))
    assert state.state == "neutro"


def test_emotional_confused():
    detector = EmotionalContextDetector()
    state = asyncio.run(detector.detect("nao entendi como assim, explica melhor"))
    assert state.state == "confuso"


def test_emotional_short_text():
    detector = EmotionalContextDetector()
    state = asyncio.run(detector.detect("oi"))
    assert state.state == "neutro"


def test_adjustment_all_states():
    for state_name in ["neutro", "urgente", "frustrado", "satisfeito", "confuso"]:
        state = EmotionalState(state=state_name)
        adj = ADJUSTMENTS.get(state_name, "")
        assert isinstance(adj, str)


def test_emotional_state_defaults():
    s = EmotionalState()
    assert s.state == "neutro"
    assert s.signals == []


# ── VoiceTones ───────────────────────────────────────────────────────────


def test_tones_generate():
    wave = VoiceTones._generate(440, 880, 80)
    assert isinstance(wave, np.ndarray)
    assert wave.dtype == np.float32
    assert len(wave) > 0


def test_tones_generate_activation():
    from unittest.mock import patch
    with patch.object(VoiceTones, '_play'):
        VoiceTones.activation_tone()


def test_tones_generate_error():
    from unittest.mock import patch
    with patch.object(VoiceTones, '_play'):
        VoiceTones.error_tone()


def test_tones_sample_rate():
    assert SAMPLE_RATE == 22050


import asyncio
