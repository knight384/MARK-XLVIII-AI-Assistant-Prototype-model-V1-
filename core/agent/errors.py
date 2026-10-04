"""core.agent.errors — agent/orchestration error taxonomy (Phase 4 spec, Part 25)."""
from __future__ import annotations


class AgentError(Exception):
    retryable: bool = False

    def __init__(self, message: str, *, agent_id: str | None = None, cause: Exception | None = None):
        super().__init__(message)
        self.agent_id = agent_id
        self.cause = cause


class AgentNotFoundError(AgentError):
    pass


class AgentRegistrationError(AgentError):
    pass


class PlanningError(AgentError):
    """Bounded planning retries exhausted."""


class InvalidPlanError(PlanningError):
    """The model produced a plan that failed structural validation."""


class OrchestrationError(AgentError):
    retryable = False


class MaxStepsExceededError(OrchestrationError):
    """Loop protection: too many execution steps (Phase 4 spec, Part 24)."""


class MaxDelegationsExceededError(OrchestrationError):
    """Loop protection: too many agent delegations."""


class TaskCancelledError(OrchestrationError):
    pass
