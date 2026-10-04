import pytest
import time
from core.goals.service import GoalService
from core.goals.store import GoalStore
from core.goals.models import GoalState
from core.goals.commitments import Commitment, CommitmentState
from core.goals.estimator import GoalEstimator

from core.awareness.tracker import AwarenessTracker
from core.awareness.signals import AwarenessSignal, SignalCategory
from core.awareness.opportunities import OpportunityEngine
from core.runtime.events import RuntimeEvent, EventBus

from core.personality.service import PersonalityService
from core.memory.service import MemoryService
from core.memory.stores.sqlite_store import SqliteMemoryStore

@pytest.fixture
def memory_service(tmp_path):
    store = SqliteMemoryStore(tmp_path / "mem.db")
    return MemoryService(preference_store=store, durable_store=store)

@pytest.fixture
def goal_service(tmp_path):
    store = GoalStore(tmp_path / "goals.db")
    return GoalService(store)

@pytest.fixture
def tracker():
    return AwarenessTracker(max_history=10)

def test_goal_lifecycle(goal_service):
    # DRAFT
    g = goal_service.create_goal("Test Goal", "Description", target_time=time.time() + 86400)
    assert g.state == GoalState.DRAFT
    
    # ACTIVE
    goal_service.start_goal(g.id)
    g = goal_service.store.get(g.id)
    assert g.state == GoalState.ACTIVE
    
    # MILESTONE
    m = goal_service.add_milestone(g.id, "M1", "First part")
    assert len(goal_service.store.get(g.id).milestones) == 1
    
    # PROGRESS
    goal_service.complete_milestone(g.id, m.id, "Done")
    g = goal_service.store.get(g.id)
    assert g.progress == 100.0
    
    # COMPLETED
    goal_service.complete_goal(g.id)
    g = goal_service.store.get(g.id)
    assert g.state == GoalState.COMPLETED
    assert g.progress == 100.0

def test_goal_estimator(goal_service):
    g = goal_service.create_goal("Est", "Desc")
    goal_service.start_goal(g.id)
    m1 = goal_service.add_milestone(g.id, "M1", "Desc")
    m2 = goal_service.add_milestone(g.id, "M2", "Desc")
    
    est = GoalEstimator()
    res = est.estimate_completion(goal_service.store.get(g.id))
    assert res["status"] == "ESTIMATED"
    assert res["confidence"] == 0.1
    
    # Complete one
    goal_service.complete_milestone(g.id, m1.id)
    # Simulate time passed
    g = goal_service.store.get(g.id)
    g.created_at = time.time() - 86400
    g.milestones[0].completed_at = time.time()
    
    res = est.estimate_completion(g)
    assert res["status"] == "ESTIMATED"
    assert res["remaining_days"] is not None
    assert res["confidence"] == 0.5

def test_commitments():
    c = Commitment(id="1", what="Finish report")
    assert c.state == CommitmentState.ACTIVE
    c.state = CommitmentState.COMPLETED
    assert c.state == CommitmentState.COMPLETED

def test_awareness_tracking(tracker):
    tracker.enable()
    tracker._on_runtime_event(RuntimeEvent("task_failed", {"task_id": "1"}))
    tracker._on_runtime_event(RuntimeEvent("goal_started", {"goal_id": "1"}))
    
    sigs = tracker.get_recent_signals()
    assert len(sigs) == 2
    assert sigs[0].category == SignalCategory.TASK_EVENT
    assert sigs[1].category == SignalCategory.GOAL_EVENT
    
    tracker.disable()
    tracker._on_runtime_event(RuntimeEvent("task_completed", {}))
    assert len(tracker.get_recent_signals()) == 2
    
def test_opportunity_engine(tracker):
    tracker.clear()
    class MockProactive:
        def should_trigger(self, _): return False
    
    engine = OpportunityEngine(MockProactive(), tracker=tracker)
    
    # 3 fails -> create mission
    tracker.add_signal(AwarenessSignal("1", SignalCategory.TASK_EVENT, "task_failed"))
    tracker.add_signal(AwarenessSignal("2", SignalCategory.TASK_EVENT, "task_failed"))
    tracker.add_signal(AwarenessSignal("3", SignalCategory.TASK_EVENT, "task_failed"))
    
    decision = engine.evaluate()
    assert decision.decision_type.name == "CREATE_MISSION"
    
def test_personality_learning(memory_service):
    svc = PersonalityService(memory_service)
    
    # Implicit learning
    p1 = svc.learn_preference("verbosity", "concise", 0.5)
    assert p1.value == "concise"
    
    # Reinforce
    p2 = svc.learn_preference("verbosity", "verbose", 0.8)
    assert svc.get_preference("verbosity").value == "verbose"
    
    # Explicit override
    p3 = svc.override_preference("verbosity", "auto")
    assert svc.get_preference("verbosity").value == "auto"
    assert svc.get_preference("verbosity").confidence == 1.0
    
    # Implicit should now be ignored
    svc.learn_preference("verbosity", "concise", 0.6)
    assert svc.get_preference("verbosity").value == "auto"
