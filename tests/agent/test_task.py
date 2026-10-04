"""tests/agent/test_task.py"""
from __future__ import annotations

from core.agent.task import StepStatus, Task, TaskStatus, TaskStep


def test_task_default_status_is_created():
    task = Task(goal="do something")
    assert task.status == TaskStatus.CREATED
    assert task.task_id


def test_task_set_status_updates_timestamp():
    task = Task(goal="x")
    before = task.updated_at
    import time
    time.sleep(0.01)
    task.set_status(TaskStatus.RUNNING)
    assert task.status == TaskStatus.RUNNING
    assert task.updated_at >= before


def test_task_step_default_status_pending():
    step = TaskStep(step_id="s1", description="do a thing")
    assert step.status == StepStatus.PENDING


def test_step_is_ready_with_no_dependencies():
    step = TaskStep(step_id="s1", description="x")
    assert step.is_ready(completed_step_ids=set(), failed_step_ids=set()) is True


def test_step_is_ready_when_dependency_completed():
    step = TaskStep(step_id="s2", description="x", dependencies=("s1",))
    assert step.is_ready(completed_step_ids={"s1"}, failed_step_ids=set()) is True
    assert step.is_ready(completed_step_ids=set(), failed_step_ids=set()) is False


def test_step_not_ready_when_dependency_failed():
    step = TaskStep(step_id="s2", description="x", dependencies=("s1",))
    assert step.is_ready(completed_step_ids=set(), failed_step_ids={"s1"}) is False


def test_task_completed_and_failed_step_ids():
    task = Task(goal="x", steps=[
        TaskStep(step_id="s1", description="a", status=StepStatus.COMPLETED),
        TaskStep(step_id="s2", description="b", status=StepStatus.FAILED),
        TaskStep(step_id="s3", description="c", status=StepStatus.PENDING),
    ])
    assert task.completed_step_ids() == {"s1"}
    assert task.failed_step_ids() == {"s2"}


def test_task_is_fully_successful():
    task = Task(goal="x", steps=[
        TaskStep(step_id="s1", description="a", status=StepStatus.COMPLETED),
        TaskStep(step_id="s2", description="b", status=StepStatus.COMPLETED),
    ])
    assert task.is_fully_successful() is True


def test_task_not_fully_successful_with_a_failure():
    task = Task(goal="x", steps=[
        TaskStep(step_id="s1", description="a", status=StepStatus.COMPLETED),
        TaskStep(step_id="s2", description="b", status=StepStatus.FAILED),
    ])
    assert task.is_fully_successful() is False


def test_task_with_no_steps_is_not_fully_successful():
    task = Task(goal="x")
    assert task.is_fully_successful() is False


def test_task_summary_contains_goal_and_status():
    task = Task(goal="build a thing", status=TaskStatus.RUNNING)
    summary = task.summary()
    assert "build a thing" in summary
    assert "RUNNING" in summary
