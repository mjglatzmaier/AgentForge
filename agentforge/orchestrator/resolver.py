"""Step reference resolver for orchestrator callables."""

from __future__ import annotations

from importlib import import_module
from typing import Any, Callable, cast

StepCallable = Callable[[dict[str, Any]], dict[str, Any]]


def resolve_ref(ref: str) -> StepCallable:
    """Resolve ``module.path:function`` into a callable."""
    if ref.count(":") != 1:
        raise ValueError(
            f"Invalid step ref '{ref}': expected format 'module.path:function'"
        )

    module_name, func_name = ref.split(":", maxsplit=1)
    if not module_name or not func_name:
        raise ValueError(
            f"Invalid step ref '{ref}': expected format 'module.path:function'"
        )

    try:
        module = import_module(module_name)
    except ModuleNotFoundError as exc:
        raise ValueError(f"Module not found for step ref '{ref}': {module_name}") from exc

    if not hasattr(module, func_name):
        raise ValueError(f"Function not found for step ref '{ref}': {func_name}")

    target = getattr(module, func_name)
    if not callable(target):
        raise TypeError(f"Resolved object is not callable for step ref '{ref}': {func_name}")

    return cast(StepCallable, target)
