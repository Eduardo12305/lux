import numpy as np


class SileroVAD:
    """Voice activity detection stub using Silero VAD."""

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold

    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        return True
