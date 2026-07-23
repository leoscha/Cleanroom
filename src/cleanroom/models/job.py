from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


class JobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    ANALYZING = "analyzing"
    SANITIZING = "sanitizing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    QUARANTINED = "quarantined"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


class JobCreate(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    source_filename: str
    source_path: str
    source_hash: str
    model: str
    policy_name: str
    policy_version: int
