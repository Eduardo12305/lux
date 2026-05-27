# lux/voice/omni_engine.py
# Módulo: Voice
# Dependências: numpy, sounddevice, asyncio
# Status: IMPLEMENTADO
# Notas: Motor unificado MiniCPM-o 4.5 via llama-omni-cli.
#   Substitui Whisper STT + LLM local + TTS em um único subprocesso.
#   Comunicação via stdin/stdout streaming. ROCm gfx1201.

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import AsyncIterator, Optional

import numpy as np

from lux.config import get_config

logger = logging.getLogger(__name__)

DEFAULT_MODEL_PATH = Path(
    "~/.lux/models/minicpm-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf"
).expanduser()

DEFAULT_BINARY_PATH = "llama-omni-cli"

# Caminho para o build compilado (prioridade sobre PATH)
OMNI_BUILD_DIR = Path("/home/luis-eduardo/services/claudio_llm/llama.cpp-omni/build/bin")

SAMPLE_RATE_IN = 16000
SAMPLE_RATE_OUT = 22050
CHUNK_DURATION_S = 0.5

GPU_ENV = {
    "HSA_OVERRIDE_GFX_VERSION": "12.0.1",
    "ROCR_VISIBLE_DEVICES": "0",
    "HIP_VISIBLE_DEVICES": "0",
}


class OmniEngine:
    """
    Backend unificado de voz + LLM via MiniCPM-o 4.5.
    Gerencia subprocesso llama-omni-cli assíncrono.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        binary_path: Optional[str] = None,
        ref_audio_path: Optional[str] = None,
        gfx_override: str = "12.0.1",
        vram_layers: int = -1,
    ):
        config = get_config()
        # Resolve e expande o caminho do modelo
        mpath = (
            model_path
            or getattr(config, "omni_model_path", None)
            or str(DEFAULT_MODEL_PATH)
        )
        self._model = Path(mpath).expanduser().resolve()

        # Resolve e expande o caminho do binário
        bin_path = (
            binary_path
            or getattr(config, "omni_binary_path", None)
            or DEFAULT_BINARY_PATH
        )
        bin_path = os.path.expanduser(bin_path)
        if not os.path.isabs(bin_path) and OMNI_BUILD_DIR.exists():
            resolved = OMNI_BUILD_DIR / bin_path
            if resolved.exists():
                bin_path = str(resolved)
        self._binary = bin_path

        # Resolve e expande o caminho do áudio de referência
        ref_path = (
            ref_audio_path
            or getattr(config, "omni_ref_audio_path", None)
        )
        self._ref_audio = os.path.expanduser(ref_path) if ref_path else None

        self._gfx = gfx_override or getattr(config, "omni_gfx_override", "12.0.1")
        self._vram = vram_layers

        self._proc: Optional[asyncio.subprocess.Process] = None
        self._ready = False
        self._started_at: float = 0.0

    async def start(self) -> None:
        if self._proc is not None and self._proc.returncode is None:
            return

        env = os.environ.copy()
        env.update(GPU_ENV)
        env["HSA_OVERRIDE_GFX_VERSION"] = self._gfx

        cmd = [
            self._binary,
            "-m", str(self._model),
            "--no-tts",
            "-ngl", str(self._vram),
        ]

        if self._ref_audio:
            cmd += ["--ref-audio", self._ref_audio]

        logger.info("Iniciando OmniEngine: %s", " ".join(cmd[:4]))

        # Redirecionar stderr para arquivo de log para evitar deadlock por buffer cheio
        log_dir = Path("~/.lux/logs").expanduser()
        log_dir.mkdir(parents=True, exist_ok=True)
        self._stderr_file = open(log_dir / "omni.log", "w", encoding="utf-8")

        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=self._stderr_file,
            env=env,
        )

        self._started_at = time.monotonic()
        self._ready = True
        logger.info("OmniEngine iniciado (PID %d)", self._proc.pid)

    async def stop(self) -> None:
        if self._proc is None:
            return
        self._ready = False

        try:
            self._proc.terminate()
            await asyncio.wait_for(self._proc.wait(), timeout=5.0)
        except (asyncio.TimeoutError, ProcessLookupError):
            try:
                self._proc.kill()
            except ProcessLookupError:
                pass
        self._proc = None

        if hasattr(self, "_stderr_file") and self._stderr_file:
            try:
                self._stderr_file.close()
            except Exception:
                pass
            self._stderr_file = None

        logger.info("OmniEngine parado")

    async def send_audio_chunk(self, pcm: np.ndarray) -> None:
        if not self._proc or self._proc.returncode is not None:
            raise RuntimeError("OmniEngine não está rodando")

        audio_bytes = pcm.astype(np.float32).tobytes()
        try:
            self._proc.stdin.write(audio_bytes)
            await self._proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            self._ready = False
            raise RuntimeError("Conexão com OmniEngine perdida")

    async def stream_response(self) -> AsyncIterator[tuple[str, Optional[np.ndarray]]]:
        if not self._proc or self._proc.returncode is not None:
            return

        buffer = b""
        chunk_size = 4096

        try:
            while self._proc.returncode is None:
                data = await asyncio.wait_for(
                    self._proc.stdout.read(chunk_size), timeout=30.0
                )
                if not data:
                    break

                text = data.decode("utf-8", errors="replace")
                for char in text:
                    yield (char, None)

        except asyncio.TimeoutError:
            logger.debug("Timeout no stream do OmniEngine")
        except (BrokenPipeError, ConnectionResetError):
            self._ready = False
        except Exception:
            logger.exception("Erro no stream do OmniEngine")

    @property
    def is_ready(self) -> bool:
        return self._ready and self._proc is not None and self._proc.returncode is None

    @property
    def uptime_seconds(self) -> float:
        if self._started_at == 0:
            return 0.0
        return time.monotonic() - self._started_at
