# lux/voice/interactive.py
# Módulo: Voice
# Dependências: voice/vad.py, voice/wake_word.py, voice/omni_engine.py, agent/agent.py
# Status: IMPLEMENTADO
# Notas: Máquina de estados do modo voz interativo.
#   Wake word → janela ativa → OmniEngine (MiniCPM-o 4.5) → classificação →
#   conversa simples (MiniCPM-o) ou tarefa complexa (Qwen3-14B + tools) → TTS com barge-in

from __future__ import annotations

import asyncio
import logging
from enum import Enum, auto
from typing import Optional

import numpy as np

from lux.voice.vad import VADDetector, FRAME_SIZE
from lux.voice.wake_word import WakeWordDetector
from lux.voice.omni_engine import OmniEngine
from lux.voice.conversation_mode import ConversationModeManager
from lux.voice.tones import VoiceTones

logger = logging.getLogger(__name__)


class InteractiveState(Enum):
    IDLE = auto()
    WAITING_FOR_WAKE = auto()
    ACTIVE_LISTENING = auto()
    PROCESSING = auto()
    SPEAKING = auto()


class VoiceMode(Enum):
    OFF = "off"
    WAKE = "wake"
    INTERACTIVE = "interactive"
    PUSH = "push"


class InteractiveListener:
    """
    Motor de voz interativo com wake word, janela de ativação e barge-in.
    
    Estados:
      IDLE → WAITING_FOR_WAKE → ACTIVE_LISTENING → PROCESSING → SPEAKING
         ↑                                                        │
         └────────────────────────────────────────────────────────┘
    
    Modos:
      WAKE        — aguarda wake word antes de ativar
      INTERACTIVE — ativa com qualquer fala (VAD)
      PUSH        — push-to-talk manual
    """

    WAKE_TIMEOUT = 8.0
    BARGE_IN_FRAMES = 4
    BASE_SILENCE_MS = 1200

    def __init__(
        self,
        vad: Optional[VADDetector] = None,
        stt=None,
        tts=None,
        wake: Optional[WakeWordDetector] = None,
        classifier: Optional = None,
    ):
        self._vad = vad or VADDetector()
        self._stt = stt or _lazy_stt()
        self._tts = tts or _lazy_tts()
        self._wake = wake or WakeWordDetector.get_instance()
        self._classifier = classifier or _lazy_classifier()
        self._mode = VoiceMode.OFF
        self._state = InteractiveState.IDLE
        self._active = False
        self._stop_event = asyncio.Event()
        self._wake_timer = 0.0
        self._voice_stream = None
        self._on_command: Optional[callable] = None

    @property
    def mode(self) -> VoiceMode:
        return self._mode

    @mode.setter
    def mode(self, value: VoiceMode):
        self._mode = value
        if value == VoiceMode.OFF:
            self._active = False
            self._stop_event.set()
        else:
            self._active = True
            self._stop_event.clear()

    @property
    def state(self) -> InteractiveState:
        return self._state

    def on_command(self, callback: callable):
        self._on_command = callback

    async def start(self):
        if self._mode == VoiceMode.OFF:
            return
        self._active = True
        self._stop_event.clear()
        self._state = InteractiveState.WAITING_FOR_WAKE
        self._wake.load()
        stream = self._vad.open_stream()
        logger.info("Modo voz interativo iniciado: %s", self._mode.value)

        try:
            while self._active and not self._stop_event.is_set():
                await self._tick(stream)
        finally:
            self._vad.close()
            await self._stt.unload()
            self._state = InteractiveState.IDLE

    async def _tick(self, stream):
        frame = stream.read(FRAME_SIZE, exception_on_overflow=False)

        if self._state == InteractiveState.SPEAKING and self._tts.is_playing:
            if self._vad.is_speech(frame):
                self._barge_in_frames = getattr(self, '_barge_count', 0) + 1
                self._barge_count = self._barge_in_frames
                if self._barge_in_frames >= self.BARGE_IN_FRAMES:
                    await self._tts.stop_playback()
                    self._state = InteractiveState.ACTIVE_LISTENING
                    logger.info("Barge-in: usuario interrompeu o TTS")
                    setattr(self, '_barge_count', 0)
                    return
            else:
                setattr(self, '_barge_count', 0)
            await asyncio.sleep(0.01)
            return

        if self._mode in (VoiceMode.WAKE, VoiceMode.INTERACTIVE):
            if self._state == InteractiveState.WAITING_FOR_WAKE:
                if self._mode == VoiceMode.WAKE:
                    if self._wake.detect(frame):
                        self._state = InteractiveState.ACTIVE_LISTENING
                        self._wake_timer = asyncio.get_event_loop().time()
                        logger.info(
                            "Wake word '%s' detectada — janela ativada",
                            self._wake.activation_word,
                        )
                else:
                    if self._vad.is_speech(frame):
                        self._state = InteractiveState.ACTIVE_LISTENING
                        self._wake_timer = asyncio.get_event_loop().time()
                        logger.info("Fala detectada — janela ativada")
                return

            if self._state == InteractiveState.ACTIVE_LISTENING:
                now = asyncio.get_event_loop().time()
                if now - self._wake_timer > self.WAKE_TIMEOUT:
                    if self._mode == VoiceMode.INTERACTIVE:
                        self._state = InteractiveState.WAITING_FOR_WAKE
                        self._wake_timer = now
                    else:
                        self._state = InteractiveState.WAITING_FOR_WAKE
                    logger.debug("Janela expirada — voltando a ouvir")
                    return

        if self._mode == VoiceMode.PUSH and self._state == InteractiveState.IDLE:
            return

    async def listen_and_process(self):
        """Push-to-talk: grava, transcreve, classifica, processa."""
        self._state = InteractiveState.ACTIVE_LISTENING

        audio = await self._vad.record_until_silence()
        if not audio:
            self._state = (
                InteractiveState.WAITING_FOR_WAKE
                if self._mode in (VoiceMode.WAKE, VoiceMode.INTERACTIVE)
                else InteractiveState.IDLE
            )
            return None

        self._state = InteractiveState.PROCESSING
        transcript = await self._stt.transcribe(audio)

        if not transcript or transcript.startswith("["):
            self._state = InteractiveState.WAITING_FOR_WAKE
            return None

        is_for_me = await self._classifier.is_for_me(transcript)
        if not is_for_me:
            logger.debug("Classificador: NAO e para mim — '%s'", transcript[:60])
            self._state = InteractiveState.WAITING_FOR_WAKE
            return None

        self._state = InteractiveState.SPEAKING
        if self._on_command:
            result = await self._on_command(transcript)
            return result

        return transcript

    async def speak_response(self, text: str):
        """Fala resposta com suporte a barge-in."""
        audio = await self._tts.synthesize(text)
        if audio:
            await self._tts.play_async(audio)
        self._state = InteractiveState.WAITING_FOR_WAKE

    def stop(self):
        self._active = False
        self._stop_event.set()

    def reset(self):
        self._stop_event.clear()
        self._state = InteractiveState.WAITING_FOR_WAKE

    # ── MiniCPM-o Continuous Loop ────────────────────────────────────────

    async def run_omni_continuous(self, omni, agent=None):
        """
        Loop principal com MiniCPM-o 4.5 como backend único.
        Suporta modos WAKE (wake word) e INTERACTIVE (VAD).
        Resposta falada via TTS com barge-in (interrupção por voz).
        Roteamento automático: tarefas complexas → Qwen3-14B + tools.
        """
        await omni.start()
        conv = ConversationModeManager()
        stream = self._vad.open_stream()
        self._voice_stream = stream
        self._agent = agent

        use_wake_word = self._mode == VoiceMode.WAKE and self._wake.is_available

        try:
            while self._active and not self._stop_event.is_set():
                if not conv.is_active:
                    frame = stream.read(FRAME_SIZE, exception_on_overflow=False)

                    if use_wake_word:
                        if not self._wake.detect(frame):
                            await asyncio.sleep(0.01)
                            continue
                        logger.info(
                            "Wake word '%s' detectada — ativando conversa",
                            self._wake.activation_word,
                        )
                    else:
                        if not self._vad.is_speech(frame):
                            await asyncio.sleep(0.01)
                            continue
                        logger.info("Fala detectada — ativando conversa")

                    conv.activate()
                    VoiceTones.activation_tone()

                silence_ms = 2500 if conv._in_conversation else 1500
                audio = await self._vad.record_until_silence(silence_threshold_ms=silence_ms)

                if audio is None:
                    if not conv.is_active:
                        conv.deactivate("timeout")
                        VoiceTones.deactivation_tone()
                    continue

                # Guarda transcrição do usuário para classificação
                user_audio = audio

                try:
                    audio_np = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
                    await omni.send_audio_chunk(audio_np)
                except RuntimeError as e:
                    logger.warning("OmniEngine indisponivel: %s", e)
                    continue

                conv.update("")

                full_text: list[str] = []
                async for text_token, audio_chunk in omni.stream_response():
                    if text_token:
                        full_text.append(text_token)

                    if audio_chunk is not None and len(audio_chunk) > 0:
                        await self._play_audio_async(audio_chunk)

                transcript = "".join(full_text)
                if not transcript.strip():
                    VoiceTones.confirmation_tone()
                    if not conv.is_active:
                        conv.deactivate("timeout")
                        VoiceTones.deactivation_tone()
                    continue

                conv.update(transcript)

                # Classifica e roteia: MiniCPM-o vs Qwen3-14B
                response_text = await self._process_with_routing(
                    omni_response=transcript,
                    user_audio=user_audio,
                )

                print(f"\n🤖 {response_text.strip()}")
                await self._speak_with_barge_in(response_text.strip())

                VoiceTones.confirmation_tone()

                if not conv.is_active:
                    conv.deactivate("timeout")
                    VoiceTones.deactivation_tone()

        finally:
            self._voice_stream = None
            self._agent = None
            self._vad.close()
            await omni.stop()

    # ── Model Routing ──────────────────────────────────────────────────────

    ACTION_KEYWORDS = frozenset({
        "criar", "crie", "escrever", "escreva", "executar", "execute",
        "rodar", "rode", "buscar", "busque", "pesquisar", "pesquise",
        "pesquisa", "procure", "procurar", "ache", "achar", "encontre", "encontrar",
        "enviar", "envie", "ler", "leia", "listar", "liste", "mostre", "mostrar",
        "deletar", "delete", "apagar", "apague", "remover", "remova",
        "mover", "mova", "renomear", "renomeie", "copiar", "copie",
        "configurar", "configure", "instalar", "instale", "setup",
        "compilar", "compile", "testar", "teste", "debug", "debugar",
        "corrigir", "corrija", "resolver", "resolva", "implementar", "implemente",
        "git", "commit", "push", "pull", "branch", "merge", "clone",
        "arquivo", "diretorio", "pasta", "caminho", "salvar", "salve",
        "email", "calendario", "lembrete", "agendar", "agende",
        "tarefa", "task", "todo",
        "web", "url", "site", "internet", "navegador", "browser",
        "screenshot", "print", "captura", "tela",
        "janela", "window", "mouse", "teclado", "click", "clicar",
        "orquestrar", "planejar", "planeje", "delegar", "subagente",
        "skill", "plugin", "cron", "fazer", "faça", "pode",
    })

    async def _process_with_routing(
        self, omni_response: str, user_audio: bytes | None = None
    ) -> str:
        """Decide se usa MiniCPM-o (leve) ou Qwen3-14B (pesado com tools)."""
        agent = getattr(self, "_agent", None)
        if not agent:
            return omni_response

        # Transcreve o áudio do usuário para classificar a intenção original
        user_text = omni_response
        if user_audio and self._stt:
            try:
                stt_text = await self._stt.transcribe(user_audio)
                if stt_text and not stt_text.startswith("[") and len(stt_text) > 3:
                    user_text = stt_text
            except Exception:
                pass

        if not self._needs_heavy_model(user_text):
            return omni_response

        logger.info("Roteando para agente pesado (Qwen3-14B + tools): '%s'", user_text[:80])
        try:
            result = await asyncio.wait_for(
                agent.run_conversation(user_message=user_text),
                timeout=120.0,
            )
            if result.final_response and result.final_response.strip():
                return result.final_response
            return omni_response
        except asyncio.TimeoutError:
            logger.warning("Agente timeout — usando resposta do MiniCPM-o")
            return omni_response
        except Exception as e:
            logger.warning("Agente falhou, usando resposta do MiniCPM-o: %s", e)
            return omni_response

    def _needs_heavy_model(self, text: str) -> bool:
        """Heurística rápida: o texto contém palavras de ação/tools?"""
        text_lower = text.lower()
        words = set(text_lower.split())
        return bool(words & self.ACTION_KEYWORDS)

    async def _speak_with_barge_in(self, text: str) -> bool:
        """Fala o texto via TTS com detecção de barge-in (interrupção por voz).
        Retorna True se o usuário interrompeu a fala."""
        if not self._tts or not self._tts._available:
            return False

        clean = self._tts._prepare_for_speech(text)
        if not clean.strip():
            return False

        audio = await self._tts.synthesize(text)
        if not audio:
            return False

        await self._tts.play_async(audio)

        speech_frames = 0
        BARGE_IN_THRESHOLD = 5

        stream = getattr(self, "_voice_stream", None)
        if not stream:
            return False

        while self._tts.is_playing:
            try:
                frame = stream.read(FRAME_SIZE, exception_on_overflow=False)
            except Exception:
                break

            if self._vad.is_speech(frame):
                speech_frames += 1
                if speech_frames >= BARGE_IN_THRESHOLD:
                    await self._tts.stop_playback()
                    logger.info("Barge-in: usuario interrompeu o TTS")
                    return True
            else:
                speech_frames = 0

            await asyncio.sleep(0.01)

        return False

    async def _play_audio_async(self, pcm: np.ndarray):
        try:
            import sounddevice as sd
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: (
                sd.play(pcm, samplerate=22050),
                sd.wait(),
            ))
        except ImportError:
            logger.debug("sounddevice nao instalado — pulando reproducao de audio")
        except Exception as e:
            logger.debug("Falha ao reproduzir audio: %s", e)


def _lazy_stt():
    try:
        from lux.voice.stt import STTEngine
        return STTEngine()
    except ImportError:
        return None


def _lazy_tts():
    try:
        from lux.voice.tts import TTSEngine
        return TTSEngine()
    except ImportError:
        return None


def _lazy_classifier():
    try:
        from lux.voice.classifier import IntentClassifier
        return IntentClassifier()
    except ImportError:
        return None
