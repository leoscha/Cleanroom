
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, sessionmaker

from cleanroom.database.models import JobRecord
from cleanroom.models.job import JobCreate, JobStatus, utcnow


class JobRepository:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory

    def create(self, data: JobCreate) -> JobRecord:
        with self.factory() as session:
            row = JobRecord(**data.model_dump(), status=JobStatus.PENDING.value)
            session.add(row)
            session.commit()
            return row

    def get(self, job_id: str) -> JobRecord | None:
        with self.factory() as session:
            return session.get(JobRecord, job_id)

    def find_by_hash(self, digest: str) -> JobRecord | None:
        with self.factory() as session:
            stmt = select(JobRecord).where(JobRecord.source_hash == digest).order_by(desc(JobRecord.created_at))
            return session.scalar(stmt)

    def update(self, job_id: str, status: JobStatus | None = None, **values: object) -> JobRecord:
        with self.factory() as session:
            row = session.get(JobRecord, job_id)
            if row is None:
                raise KeyError(job_id)
            if status is not None:
                row.status = status.value
                if status == JobStatus.PROCESSING:
                    row.started_at = utcnow()
                if status in {JobStatus.COMPLETED, JobStatus.QUARANTINED, JobStatus.FAILED,
                              JobStatus.INTERRUPTED}:
                    row.completed_at = utcnow()
            for key, value in values.items():
                if key not in {"output_path", "report_path", "findings_count", "verification_result",
                               "error_code", "error_message", "source_path"}:
                    raise ValueError(f"unsupported job field: {key}")
                setattr(row, key, value)
            session.commit()
            return row

    def list_by_status(self, statuses: set[JobStatus] | None = None, limit: int = 50,
                       offset: int = 0) -> list[JobRecord]:
        with self.factory() as session:
            stmt = select(JobRecord).order_by(desc(JobRecord.created_at)).limit(limit).offset(offset)
            if statuses:
                stmt = stmt.where(JobRecord.status.in_([item.value for item in statuses]))
            return list(session.scalars(stmt))

    def recent(self, limit: int = 20) -> list[JobRecord]:
        return self.list_by_status(limit=limit)

    def failed(self) -> list[JobRecord]:
        return self.list_by_status({JobStatus.FAILED})

    def quarantined(self) -> list[JobRecord]:
        return self.list_by_status({JobStatus.QUARANTINED})

    def eligible_retries(self) -> list[JobRecord]:
        return self.list_by_status({JobStatus.FAILED, JobStatus.INTERRUPTED})

    def recover_interrupted(self) -> int:
        active = {JobStatus.PENDING, JobStatus.PROCESSING, JobStatus.ANALYZING,
                  JobStatus.SANITIZING, JobStatus.VERIFYING}
        rows = self.list_by_status(active, limit=10000)
        for row in rows:
            self.update(row.id, JobStatus.INTERRUPTED, error_code="INTERRUPTED",
                        error_message="Processing was interrupted and is eligible for retry")
        return len(rows)
