#!/usr/bin/env python3
# scripts/test_wakeword_mic.py
# Script para testar a detecção da Wake Word de forma isolada com o microfone.

import os
import sys
import time
from pathlib import Path
from collections import deque

import numpy as np
import pyaudio

# Adiciona o diretório do projeto ao sys.path para conseguir importar o lux
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

# Carrega as configurações do arquivo .env
from dotenv import load_dotenv
load_dotenv(PROJECT_DIR / ".env")

# Configura variáveis de ambiente antes de importar
os.environ["LUX_VOICE_DEFAULT"] = "false"

from lux.voice.wake_word import WakeWordDetector


def main():
    # Inicializa o detector
    detector = WakeWordDetector.get_instance()

    print("Carregando modelos da Wake Word...")

    if not detector.load():
        print("Erro: Não foi possível carregar o detector de wake word.")
        print("Verifique se você gerou os modelos executando:")
        print("./scripts/train_wakeword.sh")
        return

    # =========================
    # CONFIGURAÇÕES
    # =========================

    SAMPLE_RATE = 16000
    CHUNK_SIZE = 480  # 30ms
    WINDOW_SAMPLES = 24000  # 1.5 segundos

    # Histórico para estabilidade temporal
    score_history = {
        word: deque(maxlen=5)
        for word in detector.configured_words
    }

    # Buffer circular
    audio_buffer = np.zeros(WINDOW_SAMPLES, dtype=np.float32)

    buffer_filled = False
    samples_since_fill = 0

    # Cooldown
    cooldown_until = 0.0

    # =========================
    # MICROFONE
    # =========================

    p = pyaudio.PyAudio()

    try:
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE,
        )

    except Exception as e:
        print(f"Erro ao abrir o microfone: {e}")
        p.terminate()
        return

    # =========================
    # INFO
    # =========================

    print("\n" + "=" * 60)
    print("         TESTADOR ISOLADO DA WAKE WORD")
    print("=" * 60)

    print(f"Modelos ativos: {detector.configured_words}")

    print(
        f"Thresholds: "
        f"{[f'{w}: {detector._thresholds[w]:.3f}' for w in detector.configured_words]}"
    )

    print(f"Limiar RMS: {detector._min_rms}")

    print("\nFale 'arkana' para testar.")
    print("Pressione Ctrl+C para encerrar.\n")

    # =========================
    # LOOP PRINCIPAL
    # =========================

    try:
        while True:

            # -------------------------
            # LEITURA DO MICROFONE
            # -------------------------

            try:
                frame = stream.read(
                    CHUNK_SIZE,
                    exception_on_overflow=False
                )

            except IOError:
                continue

            audio_np = (
                np.frombuffer(frame, dtype=np.int16)
                .astype(np.float32)
                / 32768.0
            )

            # -------------------------
            # BUFFER ROLANTE
            # -------------------------

            chunk_len = len(audio_np)

            audio_buffer = np.roll(audio_buffer, -chunk_len)
            audio_buffer[-chunk_len:] = audio_np

            samples_since_fill += chunk_len

            if samples_since_fill >= WINDOW_SAMPLES:
                buffer_filled = True

            if not buffer_filled:
                print(
                    f"\rPreenchendo buffer... "
                    f"({samples_since_fill}/{WINDOW_SAMPLES})",
                    end="",
                    flush=True
                )
                continue

            # -------------------------
            # RMS
            # -------------------------

            rms = np.sqrt(np.mean(audio_buffer ** 2))

            # -------------------------
            # COOLDOWN
            # -------------------------

            now = time.time()

            if now < cooldown_until:
                print(
                    f"\r[COOLDOWN] RMS={rms:.5f} "
                    f"| Renovando buffer...               ",
                    end="",
                    flush=True
                )
                continue

            # -------------------------
            # FILTRO DE SILÊNCIO
            # -------------------------

            if rms < detector._min_rms:
                print(
                    f"\r[SILÊNCIO] RMS={rms:.5f} "
                    f"| Ignorado                           ",
                    end="",
                    flush=True
                )

                time.sleep(0.01)
                continue

            # -------------------------
            # EXTRAÇÃO DE FEATURES
            # -------------------------

            try:
                audio_int16 = (
                    audio_buffer * 32767
                ).astype(np.int16)

                audio_batch = audio_int16[np.newaxis, :]

                features = detector._af.embed_clips(
                    audio_batch,
                    batch_size=1
                )

                feat_input = features.astype(np.float32)

            except Exception as e:
                print(
                    f"\rErro ao extrair features: {e}          ",
                    end="",
                    flush=True
                )
                continue

            # -------------------------
            # INFERÊNCIA
            # -------------------------

            scores = {}
            detected_words = []

            for word, session in detector._sessions.items():

                try:
                    input_name = session.get_inputs()[0].name

                    result = session.run(
                        None,
                        {input_name: feat_input}
                    )

                    score = float(result[0].flat[0])

                    # Proteção contra valores inválidos
                    if np.isnan(score) or np.isinf(score):
                        continue

                    # Limita score
                    score = max(0.0, min(1.0, score))

                    scores[word] = score

                    # -------------------------
                    # ESTABILIDADE TEMPORAL
                    # -------------------------

                    score_history[word].append(score)

                    avg_score = (
                        sum(score_history[word])
                        / len(score_history[word])
                    )

                    threshold = detector._thresholds.get(
                        word,
                        detector.threshold
                    )

                    # Exige:
                    # - score atual acima do threshold
                    # - média temporal acima do threshold
                    if (
                        score >= threshold
                        and avg_score >= threshold
                    ):
                        detected_words.append(word)

                except Exception:
                    continue

            # -------------------------
            # DEBUG
            # -------------------------

            debug_parts = []

            for word in scores:

                avg_score = (
                    sum(score_history[word])
                    / len(score_history[word])
                )

                debug_parts.append(
                    f"{word}: "
                    f"raw={scores[word]:.4f} "
                    f"avg={avg_score:.4f}"
                )

            scores_str = " | ".join(debug_parts)

            # -------------------------
            # DETECÇÃO
            # -------------------------

            if detected_words:

                detected_str = ", ".join(detected_words)

                print(
                    f"\r\n"
                    f"[✓ DETECTADO] "
                    f"{detected_str} "
                    f"| RMS={rms:.5f} "
                    f"| {scores_str} ✨\n",
                    flush=True
                )

                # Cooldown para limpar áudio antigo
                cooldown_until = time.time() + 2.0

                # Limpa histórico
                for word in score_history:
                    score_history[word].clear()

            else:
                print(
                    f"\r[ATIVO] "
                    f"RMS={rms:.5f} "
                    f"| {scores_str}                      ",
                    end="",
                    flush=True
                )

            # Reduz uso de CPU
            time.sleep(0.02)

    except KeyboardInterrupt:
        print("\n\nTeste encerrado pelo usuário.")

    finally:

        stream.stop_stream()
        stream.close()

        p.terminate()


if __name__ == "__main__":
    main()