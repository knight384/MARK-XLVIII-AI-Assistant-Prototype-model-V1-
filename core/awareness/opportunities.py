import logging
import time
from typing import List, Optional

from actions.proactive import ProactiveEngine, ProactiveDecision, ProactiveDecisionType
from .tracker import AwarenessTracker, get_default_tracker
from .signals import AwarenessSignal

logger = logging.getLogger(__name__)

class OpportunityEngine:
    """
    Evaluates tracked awareness signals to identify actionable opportunities.
    Delegates complex decisions to the ProactiveEngine (LLM), providing bounded context.
    Output possibilities: NO_OPPORTUNITY, SUGGEST, ASK_USER, CREATE_MISSION, DEFER.
    Never executes tools directly.
    """
    def __init__(self, proactive_engine: ProactiveEngine, tracker: Optional[AwarenessTracker] = None):
        self.proactive_engine = proactive_engine
        self.tracker = tracker or get_default_tracker()

    def evaluate(self, force: bool = False) -> Optional[ProactiveDecision]:
        """
        Evaluate recent signals for opportunities.
        """
        # Get recent signals
        signals = self.tracker.get_recent_signals(10)
        if not signals and not force:
            return ProactiveDecision(decision_type=ProactiveDecisionType.DO_NOTHING, reasoning="No recent signals.")

        # Check for explicit programmatic patterns first (e.g., repeated mission failures)
        programmatic_decision = self._check_programmatic_patterns(signals)
        if programmatic_decision:
            return programmatic_decision

        # Delegate to LLM via ProactiveEngine if it should trigger (throttle applies)
        last_speech = time.monotonic() - 1000 # stub for last user speech
        if force or self.proactive_engine.should_trigger(last_speech):
            logger.info("[OpportunityEngine] Triggering proactive check based on awareness context.")
            
            # Format context events for the LLM
            context_events = [
                f"{time.strftime('%H:%M:%S', time.localtime(s.timestamp))} - {s.category.name}: {s.type} {s.payload}"
                for s in signals
            ]
            
            prompt = self.proactive_engine.build_prompt(memory={}, context_events=context_events)
            
            # Here we would normally call the LLM Gateway, but we'll mock the extraction 
            # or rely on the caller to inject the LLM result. In an active system, 
            # this method would be async and call the gateway directly.
            
            self.proactive_engine.mark_triggered()
            
            # For synchronous architecture demonstration, we return a defer indicating
            # that LLM evaluation is requested.
            return ProactiveDecision(
                decision_type=ProactiveDecisionType.DEFER,
                reasoning="Delegated to LLM ProactiveEngine",
                action_payload={"prompt": prompt}
            )

        return ProactiveDecision(decision_type=ProactiveDecisionType.DO_NOTHING, reasoning="Rate limited or no opportunity.")

    def _check_programmatic_patterns(self, signals: List[AwarenessSignal]) -> Optional[ProactiveDecision]:
        # Example: Repeated task failure
        fails = [s for s in signals if s.type == "task_failed"]
        if len(fails) >= 3:
            return ProactiveDecision(
                decision_type=ProactiveDecisionType.CREATE_MISSION,
                reasoning="Detected 3 consecutive task failures. Suggesting a recurring mission to fix.",
                action_payload={
                    "mission_name": "Investigate Task Failures",
                    "description": "Analyze recent failed tasks and propose corrections."
                }
            )
            
        # Example: Goal deadline approaching
        at_risk = [s for s in signals if s.type == "goal_at_risk"]
        if at_risk:
            return ProactiveDecision(
                decision_type=ProactiveDecisionType.SUGGEST,
                reasoning="A goal is at risk of missing its deadline.",
                action_payload={"message": "Your active goal is at risk. Should we re-prioritize?"}
            )
            
        return None
