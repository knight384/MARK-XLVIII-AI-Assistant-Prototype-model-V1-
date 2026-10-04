"""
ProactiveEngine — context-aware background prompting.
Extended for Phase 9 to support structured decisions: DO_NOTHING, SUGGEST, ASK_USER, CREATE_MISSION, DEFER.
No hardcoded rules: we pass time + memory as context and Gemini chooses.
"""
import time
import json
import logging
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from core.notifications.service import get_notification_service, NotificationPriority

logger = logging.getLogger(__name__)

class ProactiveDecisionType(Enum):
    DO_NOTHING = "DO_NOTHING"
    SUGGEST = "SUGGEST"
    ASK_USER = "ASK_USER"
    CREATE_MISSION = "CREATE_MISSION"
    EXECUTE_APPROVED_ACTION = "EXECUTE_APPROVED_ACTION"
    DEFER = "DEFER"

@dataclass
class ProactiveDecision:
    decision_type: ProactiveDecisionType
    reasoning: str
    action_payload: Optional[Dict[str, Any]] = None

class ProactiveEngine:
    """
    Tracks silence duration, contextual events, and decides when to hand context to Gemini for a
    proactive check-in. Gemini reads the context and returns a structured ProactiveDecision.
    """

    def __init__(
        self,
        min_silence_secs: int = 900,
        check_cooldown:   int = 600,
    ):
        self.min_silence_secs = min_silence_secs
        self.check_cooldown   = check_cooldown
        self._last_triggered  = 0.0
        self.notification_svc = get_notification_service()

    def should_trigger(self, last_user_speech: float) -> bool:
        """
        Returns True only when:
          • user has been silent long enough, AND
          • enough time has passed since the last proactive message.
        """
        now     = time.monotonic()
        silence = now - last_user_speech
        gap     = now - self._last_triggered
        return silence >= self.min_silence_secs and gap >= self.check_cooldown

    def mark_triggered(self) -> None:
        self._last_triggered = time.monotonic()

    def build_prompt(self, memory: dict, context_events: list = None) -> str:
        """
        Builds the context snapshot sent to Gemini.
        Gemini reads it and decides on a structured action.
        """
        # Try to import format_memory_for_prompt, but don't fail if absent
        try:
            from memory.memory_manager import format_memory_for_prompt
            mem_str = format_memory_for_prompt(memory) or "(no user data stored yet)"
        except ImportError:
            mem_str = str(memory) if memory else "(no user data stored yet)"

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        
        silence_min = int((time.monotonic() - self._last_triggered + self.min_silence_secs) // 60)
        
        events_str = ""
        if context_events:
            events_str = "Recent Context Events:\n" + "\n".join([str(e) for e in context_events])

        return "\n".join([
            "[PROACTIVE_CHECK] You are evaluating proactive state.",
            f"Current time  : {time_str}",
            f"User silence  : {silence_min}+ minutes (they have not spoken for a while)",
            "",
            "Context about this person:",
            mem_str,
            "",
            events_str,
            "",
            "Guidelines:",
            "- Look at the time, their projects, goals, habits, and recent context events.",
            "- You must choose a structured action from the following types:",
            "  DO_NOTHING, SUGGEST, ASK_USER, CREATE_MISSION, EXECUTE_APPROVED_ACTION, DEFER.",
            "- If there is something genuinely useful, timely, or caring to say — choose SUGGEST or ASK_USER.",
            "- If the user has repetitive behavior or a lingering task, choose CREATE_MISSION.",
            "- Do not execute high-risk operations automatically.",
            "- Output your decision purely as a JSON object matching this schema:",
            "  {",
            '    "decision_type": "...",',
            '    "reasoning": "...",',
            '    "action_payload": {} // Optional data for the action',
            "  }"
        ])

    def parse_decision(self, response_text: str) -> ProactiveDecision:
        try:
            # Simple extraction in case of markdown wrapping
            text = response_text.strip()
            if text.startswith("```json"):
                text = text.replace("```json", "", 1)
            if text.endswith("```"):
                text = text[:-3]
                
            data = json.loads(text.strip())
            return ProactiveDecision(
                decision_type=ProactiveDecisionType(data["decision_type"]),
                reasoning=data["reasoning"],
                action_payload=data.get("action_payload")
            )
        except Exception as e:
            logger.error(f"[ProactiveEngine] Failed to parse decision: {e}")
            return ProactiveDecision(decision_type=ProactiveDecisionType.DO_NOTHING, reasoning="Failed to parse")

    def execute_decision(self, decision: ProactiveDecision):
        """
        Executes the proactive decision using the notification service or mission store.
        """
        if decision.decision_type == ProactiveDecisionType.DO_NOTHING:
            logger.debug("[ProactiveEngine] Decision: DO_NOTHING")
            return
            
        elif decision.decision_type == ProactiveDecisionType.DEFER:
            logger.debug(f"[ProactiveEngine] Decision: DEFER. Reasoning: {decision.reasoning}")
            # we just don't trigger anything yet
            return
            
        elif decision.decision_type in (ProactiveDecisionType.SUGGEST, ProactiveDecisionType.ASK_USER):
            message = decision.action_payload.get("message", decision.reasoning) if decision.action_payload else decision.reasoning
            self.notification_svc.notify(
                category="proactive",
                message=message,
                priority=NotificationPriority.NORMAL
            )
            
        elif decision.decision_type == ProactiveDecisionType.CREATE_MISSION:
            logger.info(f"[ProactiveEngine] Decision: CREATE_MISSION. Payload: {decision.action_payload}")
            # Note: in a fully wired system, this would call core.mission.store.MissionStore.save()
            pass
            
        elif decision.decision_type == ProactiveDecisionType.EXECUTE_APPROVED_ACTION:
            logger.info(f"[ProactiveEngine] Decision: EXECUTE_APPROVED_ACTION. Payload: {decision.action_payload}")
            # Execution must still pass through ApprovalManager if required.
            pass
