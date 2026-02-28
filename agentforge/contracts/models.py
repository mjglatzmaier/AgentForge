"""Core typed contracts shared by orchestrator, storage, and agents.

Invariants:
- Structured artifacts are represented by Pydantic models.
- Artifact identity is globally unique by logical artifact name per run.
"""

from enum import Enum
from typing import Any

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator


class Mode(str, Enum):
    """Execution mode for orchestrator and agents."""

    PROD = "prod"
    DEBUG = "debug"
    EVAL = "eval"


class StepKind(str, Enum):
    """Pipeline step implementation kind."""

    TOOL = "tool"
    AGENT = "agent"


class StepStatus(str, Enum):
    """Outcome status for a completed step."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class TriggerKind(str, Enum):
    """Trigger type for control-plane runs."""

    MANUAL = "manual"
    SCHEDULE = "schedule"
    EVENT = "event"


class TriggerSpec(BaseModel):
    """Control-plane trigger metadata snapshot for a run."""

    kind: TriggerKind
    schedule: str | None = None
    event_type: str | None = None
    source: str | None = None
    request_artifact: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("schedule", "event_type", "source", "request_artifact")
    @classmethod
    def validate_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Optional trigger fields must be non-empty when provided.")
        return normalized

    @model_validator(mode="after")
    def validate_trigger_fields(self) -> "TriggerSpec":
        if self.kind is TriggerKind.SCHEDULE:
            if self.schedule is None:
                raise ValueError("schedule is required when kind='schedule'.")
            if self.event_type is not None:
                raise ValueError("event_type is only allowed when kind='event'.")
            return self

        if self.kind is TriggerKind.EVENT:
            if self.event_type is None:
                raise ValueError("event_type is required when kind='event'.")
            if self.schedule is not None:
                raise ValueError("schedule is only allowed when kind='schedule'.")
            return self

        if self.schedule is not None:
            raise ValueError("schedule is only allowed when kind='schedule'.")
        if self.event_type is not None:
            raise ValueError("event_type is only allowed when kind='event'.")
        return self


class ControlNodeState(str, Enum):
    """Lifecycle state for a control-plane node."""

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class ControlNode(BaseModel):
    """Control-plane node contract for execution planning."""

    node_id: str
    agent_id: str
    operation: str
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    state: ControlNodeState = ControlNodeState.PENDING
    retry_policy: dict[str, Any] = Field(default_factory=dict)
    timeout_s: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("node_id", "agent_id", "operation")
    @classmethod
    def validate_non_empty_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("ControlNode string fields must be non-empty.")
        return normalized

    @field_validator("inputs", "outputs", "depends_on")
    @classmethod
    def validate_string_lists(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            normalized_item = item.strip()
            if not normalized_item:
                raise ValueError("ControlNode list entries must be non-empty.")
            normalized.append(normalized_item)
        return normalized

    @field_validator("timeout_s")
    @classmethod
    def validate_timeout(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if value <= 0:
            raise ValueError("timeout_s must be > 0 when provided.")
        return value


class ControlPlan(BaseModel):
    """Typed control-plane DAG plan with dependency validation."""

    plan_id: str
    nodes: list[ControlNode]
    max_parallel: int = 1
    policy_snapshot: dict[str, Any] = Field(default_factory=dict)
    trigger: TriggerSpec

    @field_validator("plan_id")
    @classmethod
    def validate_plan_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("plan_id must be non-empty.")
        return normalized

    @field_validator("max_parallel")
    @classmethod
    def validate_max_parallel(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_parallel must be >= 1.")
        return value

    @model_validator(mode="after")
    def validate_dag(self) -> "ControlPlan":
        node_ids = [node.node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("ControlPlan node_id values must be unique.")

        id_set = set(node_ids)
        adjacency: dict[str, list[str]] = {}
        for node in self.nodes:
            if node.node_id in node.depends_on:
                raise ValueError(f"Node '{node.node_id}' cannot depend on itself.")
            missing = [dep for dep in node.depends_on if dep not in id_set]
            if missing:
                raise ValueError(
                    f"Node '{node.node_id}' depends_on unknown node(s): {missing}"
                )
            adjacency[node.node_id] = list(node.depends_on)

        visiting: set[str] = set()
        visited: set[str] = set()

        def _visit(node_id: str) -> None:
            if node_id in visited:
                return
            if node_id in visiting:
                raise ValueError("ControlPlan dependencies contain a cycle.")
            visiting.add(node_id)
            for dependency in adjacency[node_id]:
                _visit(dependency)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in node_ids:
            _visit(node_id)
        return self


class RunConfig(BaseModel):
    """Immutable run metadata captured at pipeline start."""

    run_id: str
    timestamp: AwareDatetime
    mode: Mode
    pipeline_name: str
    git_sha: str | None = None


class ArtifactRef(BaseModel):
    """Manifest-indexed artifact descriptor produced by one pipeline step."""

    name: str
    type: str
    path: str
    sha256: str
    producer_step_id: str


class StepSpec(BaseModel):
    """Declarative pipeline step configuration."""

    id: str
    kind: StepKind
    ref: str
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def validate_non_empty_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Step id must be non-empty")
        return value


class PipelineSpec(BaseModel):
    """Ordered collection of steps to execute sequentially."""

    name: str
    steps: list[StepSpec]

    @model_validator(mode="after")
    def validate_unique_step_ids(self) -> "PipelineSpec":
        step_ids = [step.id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Step IDs must be unique")
        return self


class StepResult(BaseModel):
    """Runtime outcome for a single executed (or skipped) step."""

    step_id: str
    status: StepStatus
    started_at: AwareDatetime
    ended_at: AwareDatetime
    metrics: dict[str, float | int | str] = Field(default_factory=dict)
    outputs: list[ArtifactRef] = Field(default_factory=list)


class Manifest(BaseModel):
    """Run artifact index and step result ledger.

    Artifact identity is globally unique by artifact name.
    `producer_step_id` is metadata only.
    """

    run_id: str
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    steps: list[StepResult] = Field(default_factory=list)

    def get_artifact(self, name: str) -> ArtifactRef | None:
        """Return an artifact by global logical name, or None if absent."""
        for artifact in self.artifacts:
            if artifact.name == name:
                return artifact
        return None

    def require_artifact(self, name: str) -> ArtifactRef:
        """Return an artifact by global logical name or raise KeyError."""
        artifact = self.get_artifact(name)
        if artifact is None:
            raise KeyError(f"Artifact not found: {name}")
        return artifact

    def get_latest_by_name(self, name: str) -> ArtifactRef | None:
        """Return artifact by logical name (legacy alias for get_artifact)."""
        return self.get_artifact(name)
