# lux/speaker/enrollment.py
from __future__ import annotations
import logging
from lux.auth.models import EnrollmentResult
from lux.speaker.verifier import AudioSample, SpeakerVerifier

logger = logging.getLogger(__name__)

ENROLLMENT_PHRASES_PT = [
    "Lux, abra o terminal do projeto atual.",
    "Preciso verificar os emails nao lidos de hoje.",
    "Faca um resumo do que discutimos esta semana.",
    "Qual e o status do build no servidor de staging?",
    "Lembre-me de revisar o PR do Lucas amanha as dez horas.",
]


class EnrollmentWizard:
    def __init__(self, verifier: SpeakerVerifier):
        self._verifier = verifier

    def get_phrases(self) -> list[str]:
        return ENROLLMENT_PHRASES_PT

    async def run_enrollment(self, user_id: str, audio_samples: list[AudioSample]) -> EnrollmentResult:
        return await self._verifier.enroll(user_id, audio_samples)
