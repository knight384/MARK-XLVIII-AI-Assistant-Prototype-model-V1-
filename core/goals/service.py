import time
import uuid
import logging
from typing import Optional, List

from .models import Goal, GoalState, Milestone
from .store import GoalStore, get_default_goal_store
from core.runtime.events import get_default_bus, RuntimeEvent

logger = logging.getLogger(__name__)

class GoalService:
    """
    Manages Goal lifecycle, milestone progress, and state transitions.
    """
    def __init__(self, store: Optional[GoalStore] = None):
        self.store = store or get_default_goal_store()
        
    def create_goal(self, title: str, description: str, owner: str = "user", priority: int = 0, target_time: Optional[float] = None) -> Goal:
        goal = Goal(
            id=str(uuid.uuid4()),
            title=title,
            description=description,
            owner=owner,
            state=GoalState.DRAFT,
            priority=priority,
            target_time=target_time
        )
        self.store.save(goal)
        logger.info(f"[GoalService] Created draft goal: {goal.id} - {title}")
        return goal

    def start_goal(self, goal_id: str) -> bool:
        goal = self.store.get(goal_id)
        if not goal:
            return False
        goal.state = GoalState.ACTIVE
        goal.updated_at = time.time()
        self.store.save(goal)
        get_default_bus().publish(RuntimeEvent("goal_started", {"goal_id": goal.id}))
        return True

    def pause_goal(self, goal_id: str) -> bool:
        goal = self.store.get(goal_id)
        if not goal:
            return False
        goal.state = GoalState.PAUSED
        goal.updated_at = time.time()
        self.store.save(goal)
        return True

    def complete_goal(self, goal_id: str) -> bool:
        goal = self.store.get(goal_id)
        if not goal:
            return False
        goal.state = GoalState.COMPLETED
        goal.progress = 100.0
        goal.updated_at = time.time()
        for m in goal.milestones:
            if not m.is_completed:
                m.is_completed = True
                m.completed_at = time.time()
                m.evidence = "Implicitly completed by goal completion."
        self.store.save(goal)
        get_default_bus().publish(RuntimeEvent("goal_completed", {"goal_id": goal.id}))
        return True
        
    def add_milestone(self, goal_id: str, title: str, description: str) -> Optional[Milestone]:
        goal = self.store.get(goal_id)
        if not goal:
            return None
        m = Milestone(
            id=str(uuid.uuid4()),
            title=title,
            description=description
        )
        goal.milestones.append(m)
        self._recalculate_progress(goal)
        self.store.save(goal)
        return m

    def complete_milestone(self, goal_id: str, milestone_id: str, evidence: str = "") -> bool:
        goal = self.store.get(goal_id)
        if not goal:
            return False
        for m in goal.milestones:
            if m.id == milestone_id and not m.is_completed:
                m.is_completed = True
                m.completed_at = time.time()
                m.evidence = evidence
                self._recalculate_progress(goal)
                self.store.save(goal)
                get_default_bus().publish(RuntimeEvent("milestone_completed", {"goal_id": goal.id, "milestone_id": m.id}))
                return True
        return False

    def link_mission(self, goal_id: str, mission_id: str) -> bool:
        goal = self.store.get(goal_id)
        if not goal:
            return False
        if mission_id not in goal.related_missions:
            goal.related_missions.append(mission_id)
            goal.updated_at = time.time()
            self.store.save(goal)
        return True

    def _recalculate_progress(self, goal: Goal):
        if not goal.milestones:
            return
        completed = sum(1 for m in goal.milestones if m.is_completed)
        goal.progress = (completed / len(goal.milestones)) * 100.0

    def evaluate_risks(self):
        """
        Periodically checks active goals for risk (e.g., target_time approaching).
        """
        now = time.time()
        active = self.store.list_goals(state=GoalState.ACTIVE)
        for g in active:
            if g.target_time and g.target_time < now + (86400 * 2):  # Due within 2 days
                if g.progress < 50.0:
                    g.state = GoalState.AT_RISK
                    self.store.save(g)
                    get_default_bus().publish(RuntimeEvent("goal_at_risk", {"goal_id": g.id, "reason": "Deadline approaching with low progress"}))

_default_service: Optional[GoalService] = None

def get_default_goal_service() -> GoalService:
    global _default_service
    if _default_service is None:
        _default_service = GoalService()
    return _default_service
