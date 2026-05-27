# lux/voice/tts.py
# Módulo: Voice
# Dependências: piper (binário externo)
# Status: IMPLEMENTADO
# Notas: Piper TTS via subprocess, streaming por frase.

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from pathlib import Path
from typing import AsyncGenerator, Optional

logger = logging.getLogger(__name__)

DEFAULT_VOICE_MODEL = "pt_BR-faber-medium"
PIPER_BINARY = "piper"
PIPER_VOICE_DIR = Path("~/.lux/models/piper").expanduser()

ACRONYM_MAP = {
    "API": "á-pi-í",
    "URL": "u-erre-éle",
    "SSH": "ésse-ésse-agá",
    "HTTP": "agá-tê-tê-pê",
    "JSON": "jê-ésse-ó-éne",
    "PR": "pê-érre",
    "CLI": "cê-éle-i",
    "TTS": "tê-tê-ésse",
    "STT": "ésse-tê-tê",
}


class TTSEngine:
    """Text-to-Speech via Piper. Suporte a reproducao nao-bloqueante."""

    def __init__(
        self,
        voice: str = DEFAULT_VOICE_MODEL,
        binary: str = PIPER_BINARY,
    ):
        self._voice = voice
        self._binary = binary or PIPER_BINARY
        self._available = shutil.which(self._binary) is not None
        self._player_proc: Optional[asyncio.subprocess.Process] = None

    async def synthesize(self, text: str) -> Optional[bytes]:
        if not self._available:
            return None
        clean = self._prepare_for_speech(text)
        if not clean.strip():
            return None
        try:
            proc = await asyncio.create_subprocess_exec(
                self._binary,
                "--model", str(PIPER_VOICE_DIR / f"{self._voice}.onnx"),
                "--output-raw",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate(input=clean.encode())
            if proc.returncode == 0 and stdout:
                return stdout
            return None
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.warning("Falha no TTS: %s", e)
            return None

    async def play_async(self, audio_bytes: bytes) -> bool:
        """Reproduz audio de forma nao-bloqueante via subprocess. Suporta barge-in."""
        import tempfile
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_bytes)
                tmp_path = f.name

            player = shutil.which("ffplay") or shutil.which("mpv") or shutil.which("aplay")
            if not player:
                logger.debug("Nenhum player de audio encontrado")
                return False

            self._player_proc = await asyncio.create_subprocess_exec(
                player, "-nodisp", "-autoexit", tmp_path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            return True
        except Exception as e:
            logger.debug("Falha ao reproduzir audio: %s", e)
            return False

    async def stop_playback(self):
        """Barge-in: interrompe reproducao imediatamente."""
        if self._player_proc and self._player_proc.returncode is None:
            try:
                self._player_proc.terminate()
                await asyncio.wait_for(self._player_proc.wait(), timeout=1.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    self._player_proc.kill()
                except ProcessLookupError:
                    pass
            self._player_proc = None
            logger.debug("TTS interrompido (barge-in)")

    @property
    def is_playing(self) -> bool:
        return self._player_proc is not None and self._player_proc.returncode is None

    def _prepare_for_speech(self, text: str) -> str:
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"`[^`]+`", "", text)
        text = re.sub(r"```[\s\S]+?```", "", text)
        text = re.sub(r"#{1,6}\s+", "", text)
        text = re.sub(r"https?://\S+", "link", text)
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
        for acronym, spoken in ACRONYM_MAP.items():
            text = re.sub(rf"\b{acronym}\b", spoken, text)
        return text.strip()


class SentenceSplitter:
    """Acumula tokens e emite frases completas para TTS em streaming."""

    SENTENCE_ENDERS = {".", "!", "?", "\n", ":", ";"}

    def __init__(self):
        self._buffer: list[str] = []

    def feed(self, token: str) -> Optional[str]:
        self._buffer.append(token)
        text = "".join(self._buffer)
        if len(self._buffer) > 1 and text.rstrip()[-1] in self.SENTENCE_ENDERS:
            sentence = text.strip()
            self._buffer.clear()
            return sentence if sentence else None
        if len(text) >= 4096:
            sentence = text.strip()
            self._buffer.clear()
            return sentence if sentence else None
        return None

    def flush(self) -> Optional[str]:
        if self._buffer:
            sentence = "".join(self._buffer).strip()
            self._buffer.clear()
            return sentence if sentence else None
        return None
