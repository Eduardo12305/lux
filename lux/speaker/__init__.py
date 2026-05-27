# lux/speaker/__init__.py
# NOTA: WeSpeaker/pgvector/CommandProcessor removidos.
# MiniCPM-o 4.5 substitui toda a stack biométrica.
# Mantidos: verifier, enrollment, continuous, profile_store, lifecycle (stubs).
# Principal: OmniEngine em lux/voice/omni_engine.py

from lux.speaker.continuous import ContinuousVerifier
from lux.speaker.enrollment import EnrollmentWizard
from lux.speaker.lifecycle import ECAPALifecycleManager
from lux.speaker.profile_store import VoiceProfileStore
from lux.speaker.verifier import SpeakerVerifier

__all__ = [
    "ContinuousVerifier",
    "ECAPALifecycleManager",
    "EnrollmentWizard",
    "SpeakerVerifier",
    "VoiceProfileStore",
]
