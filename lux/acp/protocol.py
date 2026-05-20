from dataclasses import dataclass, field
import uuid
import time


@dataclass
class ACPMessage:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    sender: str = ""
    recipient: str = ""
    payload: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class ACPCapability:
    name: str
    description: str = ""
    version: str = "1.0.0"
