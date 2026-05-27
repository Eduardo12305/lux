# lux/voice/tones.py
# Módulo: Voice
# Dependências: numpy, sounddevice
# Status: IMPLEMENTADO
# Notas: Feedback sonoro gerado em CPU. 5 tons para estados do pipeline de voz.

from __future__ import annotations

import numpy as np

SAMPLE_RATE = 22050


class VoiceTones:
    """Tons de áudio para feedback do estado do Lux."""

    @staticmethod
    def _generate(freq_start, freq_end, duration_ms, volume=0.3):
        length = int(SAMPLE_RATE * duration_ms / 1000)
        t = np.linspace(0, duration_ms / 1000, length)
        freq = np.linspace(freq_start, freq_end, length)
        wave = np.sin(2 * np.pi * freq * t) * volume * np.exp(-t * 3)
        return wave.astype(np.float32)

    @staticmethod
    def _play(wave):
        try:
            import sounddevice as sd
            sd.play(wave, samplerate=SAMPLE_RATE)
            sd.wait()
        except ImportError:
            pass

    @classmethod
    def activation_tone(cls):
        """Dois bipes ascendentes: Lux ativou."""
        t1 = cls._generate(440, 880, 80)
        t2 = cls._generate(440, 880, 80)
        silence = np.zeros(int(SAMPLE_RATE * 0.05), dtype=np.float32)
        cls._play(np.concatenate([t1, silence, t2]))

    @classmethod
    def deactivation_tone(cls):
        """Bipe descendente suave: janela fechou."""
        wave = cls._generate(440, 330, 150, volume=0.2)
        cls._play(wave)

    @classmethod
    def thinking_tick(cls):
        """Tick suave durante processamento longo."""
        wave = cls._generate(440, 440, 50, volume=0.15)
        cls._play(wave)

    @classmethod
    def error_tone(cls):
        """Dois bipes curtos descendentes: erro."""
        t1 = cls._generate(880, 440, 60)
        t2 = cls._generate(880, 440, 60)
        silence = np.zeros(int(SAMPLE_RATE * 0.04), dtype=np.float32)
        cls._play(np.concatenate([t1, silence, t2]))

    @classmethod
    def confirmation_tone(cls):
        """Bipe simples: ação executada."""
        wave = cls._generate(440, 440, 50)
        cls._play(wave)
