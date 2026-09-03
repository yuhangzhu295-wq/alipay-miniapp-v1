from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EngineCandidate:
    name: str
    model: str
    available: bool
    reason: str = ""
    path: str = ""


class IdPhotoEngine:
    name = "base"
    model = ""

    def info(self) -> dict[str, Any]:
        return {"name": self.name, "model": self.model, "available": False}

