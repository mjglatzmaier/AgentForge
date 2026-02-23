from enum import Enum

from pydantic import AwareDatetime, BaseModel


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
    run_id: str
    timestamp: AwareDatetime
    mode: Mode
    pipeline_name: str
    git_sha: str | None = None


class ArtifactRef(BaseModel):
    name: str
    type: str
    path: str
    sha256: str
    producer_step_id: str
