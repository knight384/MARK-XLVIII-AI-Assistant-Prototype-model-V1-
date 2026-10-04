import logging
import uuid
import time
from typing import List, Optional

from core.memory.service import MemoryService, get_default_memory_service
from .models import PersonalityPreference

logger = logging.getLogger(__name__)

class PersonalityService:
    """
    Manages personality preferences and learning.
    Backed by MemoryService. Preferences are bounded and reversible.
    """
    def __init__(self, memory_service: Optional[MemoryService] = None):
        self.memory = memory_service or get_default_memory_service()
        self._learning_enabled = True

    def toggle_learning(self, enabled: bool):
        self._learning_enabled = enabled

    def get_preference(self, category: str) -> Optional[PersonalityPreference]:
        # MemoryService search (ProjectID=personality, or use namespace)
        # Using existing preference storage conceptually
        from core.memory.models import RetrievalQuery, MemoryType
        results = self.memory.retrieve(RetrievalQuery(namespace="personality", tags=(category,)))
        records = [r.record for r in results]
        if records:
            # Sort by confidence and updated_at
            best = sorted(records, key=lambda r: (r.confidence, r.updated_at), reverse=True)[0]
            if "disabled" in best.metadata and best.metadata["disabled"]:
                return None
            return PersonalityPreference.from_dict(best.metadata["preference"])
        return None

    def get_all_preferences(self) -> List[PersonalityPreference]:
        from core.memory.models import RetrievalQuery
        results = self.memory.retrieve(RetrievalQuery(namespace="personality"))
        records = [r.record for r in results]
        prefs = []
        for r in records:
            if "preference" in r.metadata:
                prefs.append(PersonalityPreference.from_dict(r.metadata["preference"]))
        return prefs

    def learn_preference(self, category: str, value: str, confidence: float = 0.5) -> Optional[PersonalityPreference]:
        """
        Bounded learning. Replaces or reinforces existing preferences for a category.
        """
        if not self._learning_enabled and confidence < 1.0:
            logger.debug("[PersonalityService] Learning disabled, ignoring implicit preference.")
            return None
            
        existing = self.get_preference(category)
        if existing and existing.confidence >= 1.0 and confidence < 1.0:
            logger.debug(f"[PersonalityService] Ignoring implicit '{category}' preference due to existing explicit override.")
            return existing

        pref = PersonalityPreference(
            id=str(uuid.uuid4()),
            category=category,
            value=value,
            confidence=confidence
        )
        self._save_to_memory(pref)
        logger.info(f"[PersonalityService] Learned preference: {category} = {value} (conf: {confidence})")
        return pref

    def override_preference(self, category: str, value: str) -> PersonalityPreference:
        """
        Explicit user override. Confidence = 1.0.
        """
        pref = PersonalityPreference(
            id=str(uuid.uuid4()),
            category=category,
            value=value,
            confidence=1.0
        )
        self._save_to_memory(pref)
        return pref

    def delete_preference(self, preference_id: str) -> bool:
        from core.memory.models import RetrievalQuery, MemoryType
        results = self.memory.retrieve(RetrievalQuery(namespace="personality"))
        records = [r.record for r in results]
        for r in records:
            if r.metadata.get("preference", {}).get("id") == preference_id:
                self.memory.forget(r.memory_id, r.memory_type)
                return True
        return False

    def disable_preference(self, preference_id: str) -> bool:
        from core.memory.models import RetrievalQuery
        results = self.memory.retrieve(RetrievalQuery(namespace="personality"))
        records = [r.record for r in results]
        for r in records:
            if r.metadata.get("preference", {}).get("id") == preference_id:
                pref_data = r.metadata["preference"]
                pref_data["disabled"] = True
                pref_data["updated_at"] = time.time()
                r.metadata["preference"] = pref_data
                self.memory.update(r)
                return True
        return False

    def _save_to_memory(self, pref: PersonalityPreference):
        from core.memory.models import MemoryRecord, MemoryType, RetrievalQuery
        # Clean up old records for this category
        results = self.memory.retrieve(RetrievalQuery(namespace="personality", tags=(pref.category,)))
        for res in results:
            self.memory.forget(res.record.memory_id, res.record.memory_type)

        record = self.memory.remember(
            content=f"User prefers {pref.category} to be {pref.value}.",
            memory_type=MemoryType.SEMANTIC,
            namespace="personality",
            tags=(pref.category, "preference"),
            importance=pref.confidence
        )
        if record:
            record.metadata = {"preference": pref.to_dict()}
            record.confidence = pref.confidence
            self.memory.update(record)

_default_service: Optional[PersonalityService] = None

def get_default_personality_service() -> PersonalityService:
    global _default_service
    if _default_service is None:
        _default_service = PersonalityService()
    return _default_service
