from lux.voice.stt import WhisperSTT
from lux.voice.tts import PiperTTS
from lux.voice.vad import SileroVAD


class VoicePipeline:
    """Orchestrates STT -> processing -> TTS pipeline."""

    def __init__(self, stt: WhisperSTT, tts: PiperTTS, vad: SileroVAD):
        self.stt = stt
        self.tts = tts
        self.vad = vad

    async def run(self, audio_path: str) -> str:
        text = await self.stt.transcribe(audio_path)
        return text
