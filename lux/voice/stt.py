import asyncio
from pathlib import Path


class WhisperSTT:
    """Speech-to-text using whisper.cpp via subprocess."""

    def __init__(self, model_path: Path, binary_path: Path = Path("whisper-cli")):
        self.model_path = model_path
        self.binary_path = binary_path

    async def transcribe(self, audio_path: Path) -> str:
        proc = await asyncio.create_subprocess_exec(
            str(self.binary_path),
            "-m", str(self.model_path),
            "-f", str(audio_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await proc.communicate()
        return stdout.decode().strip()
