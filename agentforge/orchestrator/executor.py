"""Step execution runtime abstractions for orchestrator."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from pydantic import Field

from agentforge.contracts.models import StepResult, StepSpec, StepStatus
from agentforge.orchestrator.resolver import resolve_ref


class StepExecutionResult(StepResult):
    """Executor return shape including raw step payload."""

    raw_output: dict[str, Any] = Field(default_factory=dict)


class StepExecutor(ABC):
    """Runtime boundary for step execution implementations."""

    @abstractmethod
    def execute(self, step: StepSpec, context: dict[str, Any]) -> StepResult:
        """Execute one step and return runtime metadata."""


class InProcExecutor(StepExecutor):
    """Execute steps by resolving and invoking Python callables in-process."""

    def execute(self, step: StepSpec, context: dict[str, Any]) -> StepResult:
        started_at = _utcnow()
        step_callable = resolve_ref(step.ref)
        returned = step_callable(context)
        ended_at = _utcnow()
        if not isinstance(returned, dict):
            raise TypeError(f"Step '{step.id}' must return a dict.")
        return StepExecutionResult(
            step_id=step.id,
            status=StepStatus.SUCCESS,
            started_at=started_at,
            ended_at=ended_at,
            metrics={},
            outputs=[],
            raw_output=returned,
        )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
