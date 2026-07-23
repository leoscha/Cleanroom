from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from cleanroom.models.job import JobStatus, utcnow


class Base(DeclarativeBase):
    pass


class JobRecord(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_filename: Mapped[str] = mapped_column(String(255))
    source_path: Mapped[str] = mapped_column(String(2048))
    source_hash: Mapped[str] = mapped_column(String(64), index=True)
    output_path: Mapped[str | None] = mapped_column(String(2048))
    report_path: Mapped[str | None] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.PENDING.value, index=True)
    model: Mapped[str] = mapped_column(String(255))
    policy_name: Mapped[str] = mapped_column(String(255))
    policy_version: Mapped[int] = mapped_column(Integer)
    findings_count: Mapped[int] = mapped_column(Integer, default=0)
    verification_result: Mapped[bool | None] = mapped_column(Boolean)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
