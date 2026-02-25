import pytest

from agentforge.orchestrator.resolver import resolve_ref


def test_resolve_ref_resolves_known_callable() -> None:
    resolved = resolve_ref("math:sqrt")
    assert resolved(9) == 3


def test_resolve_ref_rejects_bad_format() -> None:
    with pytest.raises(ValueError, match="expected format"):
        resolve_ref("math.sqrt")


def test_resolve_ref_rejects_missing_module() -> None:
    with pytest.raises(ValueError, match="Module not found"):
        resolve_ref("this_module_should_not_exist_xyz:run")


def test_resolve_ref_rejects_missing_function() -> None:
    with pytest.raises(ValueError, match="Function not found"):
        resolve_ref("math:does_not_exist")


def test_resolve_ref_rejects_non_callable_object() -> None:
    with pytest.raises(TypeError, match="not callable"):
        resolve_ref("math:pi")
