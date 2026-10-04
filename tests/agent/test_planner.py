"""tests/agent/test_planner.py"""
from __future__ import annotations

import pytest
from .conftest import make_fake_gateway

from core.agent.errors import InvalidPlanError
from core.agent.planner import Planner


@pytest.mark.asyncio
async def test_valid_plan_parses():
    gateway, provider = make_fake_gateway(
        '{"goal": "g", "steps": [{"id": "step-1", "description": "search the web", '
        '"required_capabilities": ["research"], "dependencies": []}]}'
    )
    planner = Planner(model_gateway=gateway)
    steps = await planner.plan("research something")
    assert len(steps) == 1
    assert steps[0].step_id == "step-1"
    assert steps[0].required_capabilities == ("research",)


@pytest.mark.asyncio
async def test_plan_with_markdown_fences_is_parsed():
    gateway, _ = make_fake_gateway(
        '```json\n{"goal": "g", "steps": [{"id": "s1", "description": "x", '
        '"required_capabilities": ["research"]}]}\n```'
    )
    planner = Planner(model_gateway=gateway)
    steps = await planner.plan("goal")
    assert len(steps) == 1


@pytest.mark.asyncio
async def test_plan_with_dependencies():
    gateway, _ = make_fake_gateway(
        '{"goal": "g", "steps": ['
        '{"id": "s1", "description": "a", "required_capabilities": ["research"]}, '
        '{"id": "s2", "description": "b", "required_capabilities": ["coding"], "dependencies": ["s1"]}'
        ']}'
    )
    planner = Planner(model_gateway=gateway)
    steps = await planner.plan("goal")
    assert steps[1].dependencies == ("s1",)


@pytest.mark.asyncio
async def test_invalid_json_raises_after_bounded_retries():
    gateway, provider = make_fake_gateway("not json at all")
    planner = Planner(model_gateway=gateway, max_attempts=2)
    with pytest.raises(InvalidPlanError):
        await planner.plan("goal")
    assert len(provider.calls) == 2  # exactly max_attempts, not unbounded


@pytest.mark.asyncio
async def test_missing_steps_key_raises():
    gateway, _ = make_fake_gateway('{"goal": "g"}')
    planner = Planner(model_gateway=gateway, max_attempts=1)
    with pytest.raises(InvalidPlanError):
        await planner.plan("goal")


@pytest.mark.asyncio
async def test_empty_steps_list_raises():
    gateway, _ = make_fake_gateway('{"goal": "g", "steps": []}')
    planner = Planner(model_gateway=gateway, max_attempts=1)
    with pytest.raises(InvalidPlanError):
        await planner.plan("goal")


@pytest.mark.asyncio
async def test_step_missing_description_raises():
    gateway, _ = make_fake_gateway('{"goal": "g", "steps": [{"id": "s1", "required_capabilities": ["research"]}]}')
    planner = Planner(model_gateway=gateway, max_attempts=1)
    with pytest.raises(InvalidPlanError):
        await planner.plan("goal")


@pytest.mark.asyncio
async def test_step_with_invalid_capability_raises():
    gateway, _ = make_fake_gateway(
        '{"goal": "g", "steps": [{"id": "s1", "description": "x", "required_capabilities": ["time_travel"]}]}'
    )
    planner = Planner(model_gateway=gateway, max_attempts=1)
    with pytest.raises(InvalidPlanError):
        await planner.plan("goal")


@pytest.mark.asyncio
async def test_step_with_no_capabilities_raises():
    gateway, _ = make_fake_gateway(
        '{"goal": "g", "steps": [{"id": "s1", "description": "x", "required_capabilities": []}]}'
    )
    planner = Planner(model_gateway=gateway, max_attempts=1)
    with pytest.raises(InvalidPlanError):
        await planner.plan("goal")


@pytest.mark.asyncio
async def test_duplicate_step_ids_raises():
    gateway, _ = make_fake_gateway(
        '{"goal": "g", "steps": ['
        '{"id": "s1", "description": "a", "required_capabilities": ["research"]}, '
        '{"id": "s1", "description": "b", "required_capabilities": ["research"]}'
        ']}'
    )
    planner = Planner(model_gateway=gateway, max_attempts=1)
    with pytest.raises(InvalidPlanError):
        await planner.plan("goal")


@pytest.mark.asyncio
async def test_unknown_dependency_reference_raises():
    gateway, _ = make_fake_gateway(
        '{"goal": "g", "steps": [{"id": "s1", "description": "a", '
        '"required_capabilities": ["research"], "dependencies": ["nonexistent"]}]}'
    )
    planner = Planner(model_gateway=gateway, max_attempts=1)
    with pytest.raises(InvalidPlanError):
        await planner.plan("goal")


@pytest.mark.asyncio
async def test_planner_never_loops_unboundedly():
    """Regardless of max_attempts configured, the number of model calls
    must be exactly bounded — never open-ended."""
    gateway, provider = make_fake_gateway("garbage")
    planner = Planner(model_gateway=gateway, max_attempts=5)
    with pytest.raises(InvalidPlanError):
        await planner.plan("goal")
    assert len(provider.calls) == 5
