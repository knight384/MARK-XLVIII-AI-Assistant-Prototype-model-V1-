import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from core.goals.service import get_default_goal_service
from core.personality.service import get_default_personality_service
from core.awareness.tracker import get_default_tracker
from core.runtime.events import get_default_bus, RuntimeEvent

def main():
    print("Starting Live Verification for Phase 10...")
    
    # Goals
    g_svc = get_default_goal_service()
    g = g_svc.create_goal("Test Goal", "Goal for Phase 10 Verification", target_time=2000000000)
    g_svc.start_goal(g.id)
    m = g_svc.add_milestone(g.id, "M1", "Milestone 1")
    g_svc.complete_milestone(g.id, m.id, "Completed via verify script")
    g = g_svc.store.get(g.id)
    print(f"Goal status: {g.state.name}, Progress: {g.progress}%")
    
    # Personality
    p_svc = get_default_personality_service()
    p = p_svc.learn_preference("verbosity", "concise", 0.8)
    if p:
        print(f"Learned Personality: {p.category} = {p.value} (conf: {p.confidence})")
    
    # Awareness
    tracker = get_default_tracker()
    tracker.start()
    bus = get_default_bus()
    bus.publish(RuntimeEvent("task_failed", {"task_id": "test-task-1"}))
    
    import time
    time.sleep(0.5)
    
    signals = tracker.get_recent_signals()
    for s in signals:
        print(f"Awareness tracked signal: {s.category.name} - {s.type} - {s.payload}")
        
    print("Live verification complete.")

if __name__ == "__main__":
    main()
