import logging
from typing import Optional
from .models import Goal, GoalState

logger = logging.getLogger(__name__)

class GoalEstimator:
    """
    Estimates goal completion timeframe and effort based on bounded progress metrics.
    Clearly distinguishes between measured and estimated.
    """
    
    def estimate_completion(self, goal: Goal) -> dict:
        if goal.state == GoalState.COMPLETED:
            return {"status": "MEASURED", "remaining_days": 0, "confidence": 1.0}
            
        if not goal.milestones:
            # Without milestones, we can't reliably extrapolate progress natively.
            return {"status": "INFERRED", "remaining_days": None, "confidence": 0.0}
            
        completed = [m for m in goal.milestones if m.is_completed and m.completed_at]
        if not completed:
            return {"status": "ESTIMATED", "remaining_days": None, "confidence": 0.1, "reason": "No measured progress."}
            
        # Basic linear extrapolation
        first_completion = min(m.completed_at for m in completed)
        now = max(m.completed_at for m in completed)
        
        elapsed = now - goal.created_at
        if elapsed <= 0 or goal.progress <= 0:
            return {"status": "ESTIMATED", "remaining_days": None, "confidence": 0.1}
            
        rate = goal.progress / elapsed
        remaining_progress = 100.0 - goal.progress
        estimated_remaining_time = remaining_progress / rate
        
        remaining_days = estimated_remaining_time / 86400
        
        return {
            "status": "ESTIMATED", 
            "remaining_days": round(remaining_days, 1), 
            "confidence": min(0.9, len(completed) / len(goal.milestones))
        }
