"""Sequential pipeline runner orchestration.

Runner responsibilities include run directory creation, manifest updates, and
step execution bookkeeping without agent-specific logic coupling.
"""

from __future__ import annotations

from typing import Any

from agentforge.contracts.models import StepSpec


def validate_step_outputs(step: StepSpec, returned: dict[str, Any]) -> None:
    """Validate that returned output keys match step output declarations exactly."""
    if not isinstance(returned, dict):
        raise TypeError(
            f"Step '{step.id}' must return a dict of outputs keyed by declared names."
        )

    expected = set(step.outputs)
    actual = set(returned.keys())
    missing = sorted(expected - actual)
    undeclared = sorted(actual - expected)

    if missing or undeclared:
        parts: list[str] = []
        if missing:
            parts.append(f"missing outputs: {missing}")
        if undeclared:
            parts.append(f"undeclared outputs: {undeclared}")
        detail = "; ".join(parts)
        raise ValueError(f"Step '{step.id}' output contract violation: {detail}")
