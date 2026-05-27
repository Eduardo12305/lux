# lux/speaker/continuous.py
from __future__ import annotations
import logging
from lux.auth.models import AuthSession, ContinuityResult
from lux.speaker.verifier import AudioSample, SpeakerVerifier

logger = logging.getLogger(__name__)


class ContinuousVerifier:
    VERIFY_EVERY_N_VOICE_TURNS = 10
    DRIFT_THRESHOLD = -0.10

    def __init__(self, verifier: SpeakerVerifier):
        self._verifier = verifier

    async def check_session_continuity(
        self, session: AuthSession, audio: AudioSample
    ) -> ContinuityResult:
        embedding = await self._verifier.extract_embedding(audio)
        if embedding is None:
            return ContinuityResult(same_speaker=False, confidence=0.0, action="REAUTH")

        result = await self._verifier.verify(session.user_id, audio)
        if result.method == "ACCEPTED":
            if result.confidence >= 0.88:
                return ContinuityResult(same_speaker=True, confidence=result.confidence, action="CONTINUE")
            return ContinuityResult(same_speaker=True, confidence=result.confidence, action="WARN")
        elif result.method == "FALLBACK_NEEDED":
            return ContinuityResult(same_speaker=False, confidence=result.confidence, action="REAUTH")
        return ContinuityResult(same_speaker=False, confidence=0.0, action="INVALIDATE")
