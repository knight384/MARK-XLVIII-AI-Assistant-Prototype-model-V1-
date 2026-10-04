import pytest
import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.mission.models import Mission, MissionState, TriggerType
from core.mission.store import MissionStore

@pytest.fixture
def store(tmp_path):
    s = MissionStore(tmp_path / "test_missions.db")
    yield s
    s.close()

def test_mission_lifecycle(store):
    m = Mission(
        id="m1",
        name="Test",
        description="test",
        owner="user",
        state=MissionState.DRAFT,
        trigger_type=TriggerType.MANUAL,
        created_at=time.time(),
        updated_at=time.time()
    )
    store.save(m)
    
    fetched = store.get("m1")
    assert fetched.id == "m1"
    assert fetched.state == MissionState.DRAFT
    
    fetched.state = MissionState.SCHEDULED
    store.save(fetched)
    
    ready = store.list_missions(state=MissionState.SCHEDULED)
    assert len(ready) == 1
    assert ready[0].id == "m1"

def test_proactive_engine():
    from actions.proactive import ProactiveEngine, ProactiveDecisionType
    engine = ProactiveEngine()
    
    # Simulate a JSON response from LLM
    json_resp = '{"decision_type": "SUGGEST", "reasoning": "User has been quiet", "action_payload": {"message": "Hello"}}'
    decision = engine.parse_decision(json_resp)
    
    assert decision.decision_type == ProactiveDecisionType.SUGGEST
    assert decision.reasoning == "User has been quiet"
    assert decision.action_payload["message"] == "Hello"

def test_notification_policy():
    from core.notifications.service import NotificationService, NotificationPriority
    svc = NotificationService()
    svc.cooldown_ms = 5000  # 5s cooldown
    # Disable quiet hours for the test
    svc.quiet_hours_start = 25
    svc.quiet_hours_end = -1
    
    # First notify should work
    res = svc.notify("test", "hello")
    assert res is True
    
    # Second should hit cooldown
    res2 = svc.notify("test", "hello again")
    assert res2 is False
    
    # Urgent bypasses cooldown and quiet hours
    res3 = svc.notify("test", "URGENT!", priority=NotificationPriority.URGENT)
    assert res3 is True
