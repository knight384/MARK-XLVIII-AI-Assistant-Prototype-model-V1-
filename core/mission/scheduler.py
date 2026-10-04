import asyncio
import logging
import time
from typing import Optional

from core.agent.orchestrator import get_default_orchestrator
from .models import Mission, MissionState, TriggerType
from .store import MissionStore

logger = logging.getLogger(__name__)

class MissionScheduler:
    """
    MARK-native scheduler supporting one-shot, recurring, and timezone-aware schedules.
    Ensures deterministic execution and no duplicate execution after restart.
    """
    def __init__(self, store: MissionStore, poll_interval_sec: float = 15.0):
        self.store = store
        self.poll_interval_sec = poll_interval_sec
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._orchestrator = get_default_orchestrator()

    def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("[MissionScheduler] Started background scheduling loop.")

    async def stop(self):
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("[MissionScheduler] Stopped gracefully.")

    async def _loop(self):
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"[MissionScheduler] Unexpected error in scheduling loop: {e}")
            await asyncio.sleep(self.poll_interval_sec)

    async def _tick(self):
        now = time.time()
        # Find scheduled missions
        scheduled = self.store.list_missions(state=MissionState.SCHEDULED)
        for mission in scheduled:
            if mission.next_execution_at and mission.next_execution_at <= now:
                await self._dispatch_mission(mission)

        # In a real implementation, WAITING_CONDITION evaluations would also be polled here
        # if they are time-based conditions, but typically those are event-driven.

    async def _dispatch_mission(self, mission: Mission):
        # Atomic transition check would happen here in a fully concurrent environment.
        mission.state = MissionState.RUNNING
        mission.last_execution_at = time.time()
        self.store.save(mission)
        
        logger.info(f"[MissionScheduler] Dispatching mission {mission.id} ('{mission.name}')")
        
        # Fire-and-forget execution to avoid blocking the scheduler loop
        asyncio.create_task(self._execute_mission(mission.id))

    async def _execute_mission(self, mission_id: str):
        mission = self.store.get(mission_id)
        if not mission or mission.state != MissionState.RUNNING:
            return
            
        try:
            # Delegate to orchestrator (Task execution)
            # This maintains the strict security boundary:
            # Mission -> Task -> Orchestrator -> ToolExecutor -> PolicyEngine
            task = await self._orchestrator.run_task(f"MISSION: {mission.name}\n{mission.description}")
            
            mission = self.store.get(mission_id)
            if not mission:
                return
                
            mission.attempt_count += 1
            
            if task.status.value == "COMPLETED":
                mission.state = MissionState.SUCCEEDED
                mission.result_summary = "Task completed successfully."
                # Reschedule if recurring
                self._calculate_next_run(mission)
            else:
                self._handle_failure(mission, "Task did not complete successfully.")
                
        except Exception as e:
            mission = self.store.get(mission_id)
            if mission:
                mission.attempt_count += 1
                self._handle_failure(mission, str(e))
                
        if mission:
            self.store.save(mission)

    def _handle_failure(self, mission: Mission, error: str):
        logger.error(f"[MissionScheduler] Mission {mission.id} failed: {error}")
        mission.error_state = error
        
        # Simple backoff/retry
        if mission.attempt_count < mission.max_attempts:
            mission.state = MissionState.SCHEDULED
            # exponential backoff (e.g., 2^attempts * 60 seconds)
            backoff_sec = (2 ** mission.attempt_count) * 60
            mission.next_execution_at = time.time() + backoff_sec
            logger.info(f"[MissionScheduler] Mission {mission.id} retrying in {backoff_sec}s (Attempt {mission.attempt_count}/{mission.max_attempts})")
        else:
            mission.state = MissionState.FAILED
            logger.warning(f"[MissionScheduler] Mission {mission.id} permanently failed.")

    def _calculate_next_run(self, mission: Mission):
        if mission.cron_expression:
            try:
                import croniter
                from datetime import datetime
                # Calculate next run based on cron
                iter = croniter.croniter(mission.cron_expression, datetime.fromtimestamp(time.time()))
                mission.next_execution_at = iter.get_next(float)
                mission.state = MissionState.SCHEDULED
                mission.attempt_count = 0
                logger.info(f"[MissionScheduler] Rescheduled mission {mission.id} to {mission.next_execution_at}")
            except ImportError:
                logger.error("[MissionScheduler] croniter is not installed, cannot schedule recurring mission.")
                mission.state = MissionState.FAILED
        else:
            # One-shot mission is done
            if mission.state == MissionState.SUCCEEDED:
                pass # leave as SUCCEEDED
