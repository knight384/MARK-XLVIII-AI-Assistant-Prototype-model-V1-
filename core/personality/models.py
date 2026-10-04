from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class PersonalityPreference:
    """
    A learned or explicit preference that affects presentation/communication.
    Does NOT affect security or policy.
    """
    id: str
    category: str # e.g. "verbosity", "tone", "notification_style"
    value: str
    confidence: float = 1.0  # 0.0 to 1.0 (1.0 = explicit override)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    disabled: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "value": self.value,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "disabled": self.disabled
        }

    @classmethod
    def from_dict(cls, data: dict) -> PersonalityPreference:
        return cls(
            id=data["id"],
            category=data["category"],
            value=data["value"],
            confidence=data.get("confidence", 1.0),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            disabled=data.get("disabled", False)
        )
