"""core.agent.registry — the Agent Registry (Phase 4 spec, Part 4)."""
from __future__ import annotations

import threading

from .base import Agent, AgentCapability
from .errors import AgentRegistrationError


class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, Agent] = {}
        self._lock = threading.Lock()

    def register(self, agent: Agent) -> None:
        with self._lock:
            if agent.agent_id in self._agents:
                raise AgentRegistrationError(
                    f"An agent with id '{agent.agent_id}' is already registered.", agent_id=agent.agent_id,
                )
            self._agents[agent.agent_id] = agent

    def unregister(self, agent_id: str) -> None:
        with self._lock:
            self._agents.pop(agent_id, None)

    def get(self, agent_id: str) -> Agent | None:
        return self._agents.get(agent_id)

    def exists(self, agent_id: str) -> bool:
        return agent_id in self._agents

    def list(self) -> list[Agent]:
        return list(self._agents.values())

    def list_ids(self) -> list[str]:
        return list(self._agents.keys())

    def find_by_capability(self, capability: AgentCapability) -> list[Agent]:
        return [a for a in self._agents.values() if capability in a.metadata.capabilities]


_default_registry: AgentRegistry | None = None
_default_lock = threading.Lock()


def get_default_agent_registry() -> AgentRegistry:
    global _default_registry
    with _default_lock:
        if _default_registry is None:
            from .agents import register_all_agents
            registry = AgentRegistry()
            register_all_agents(registry)
            _default_registry = registry
        return _default_registry
