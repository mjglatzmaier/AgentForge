"""Core typed contracts shared by orchestrator, storage, and agents.

Invariants:
- Structured artifacts are represented by Pydantic models.
- Artifact identity is the compound key (producer_step_id, name).
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

    Artifact identity is compound: (producer_step_id, name).
    """

    run_id: str
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    steps: list[StepResult] = Field(default_factory=list)

    def get_artifact(self, producer_step_id: str, name: str) -> ArtifactRef | None:
        """Return an artifact by compound key, or None if absent."""
        for artifact in self.artifacts:
            if artifact.producer_step_id == producer_step_id and artifact.name == name:
                return artifact
        return None

    def require_artifact(self, producer_step_id: str, name: str) -> ArtifactRef:
        """Return an artifact by compound key or raise KeyError."""
        artifact = self.get_artifact(producer_step_id, name)
        if artifact is None:
            raise KeyError(f"Artifact not found: ({producer_step_id}, {name})")
        return artifact

    def get_latest_by_name(self, name: str) -> ArtifactRef | None:
        """Return the most recently registered artifact with the given logical name."""
        for artifact in reversed(self.artifacts):
            if artifact.name == name:
                return artifact
        return None
