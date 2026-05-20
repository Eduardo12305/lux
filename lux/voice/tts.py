import asyncio
from pathlib import Path


class PiperTTS:
    """Text-to-speech using Piper via subprocess."""

    def __init__(self, model_path: Path, binary_path: Path = Path("piper")):
        self.model_path = model_path
        self.binary_path = binary_path

    async def synthesize(self, text: str, output_path: Path) -> None:
        proc = await asyncio.create_subprocess_exec(
            str(self.binary_path),
            "-m", str(self.model_path),
            "--output_file", str(output_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate(input=text.encode())
