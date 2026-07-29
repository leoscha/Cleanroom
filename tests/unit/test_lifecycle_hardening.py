import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from cleanroom.database.repository import JobRepository
from cleanroom.database.session import create_db_engine, initialize_database, session_factory
from cleanroom.files import workspace_lock
from cleanroom.files.manifest import JobManifest, clean_manifests
from cleanroom.files.workspace_lock import WorkspaceBusyError, WorkspaceLock
from cleanroom.models.job import JobCreate, JobStatus


def _repository(url: str) -> JobRepository:
    engine = create_db_engine(url)
    initialize_database(engine)
    return JobRepository(session_factory(engine))


def test_second_workspace_lock_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "workspace.lock"
    with WorkspaceLock(path), pytest.raises(WorkspaceBusyError), WorkspaceLock(path):
        pass
    with WorkspaceLock(path):
        pass


def test_windows_workspace_lock_unlocks_the_acquired_byte(
    tmp_path: Path, monkeypatch
) -> None:
    positions: list[int] = []

    def locking(descriptor: int, mode: int, count: int) -> None:
        assert mode in {1, 2} and count == 1
        positions.append(os.lseek(descriptor, 0, os.SEEK_CUR))

    fake_msvcrt = SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2, locking=locking)
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
    monkeypatch.setattr(workspace_lock.os, "name", "nt")
    path = tmp_path / "windows-workspace.lock"
    with WorkspaceLock(path):
        pass
    assert positions == [0, 0]


def test_manifest_and_interrupted_recovery(tmp_path: Path) -> None:
    manifests = tmp_path / "tmp"
    manifest = JobManifest(manifests, "job-id", "safe.txt")
    manifest.update("detecting")
    assert manifest.path is not None and manifest.path.exists()
    assert clean_manifests(manifests) == 1

    repo = _repository(f"sqlite:///{tmp_path / 'jobs.db'}")
    row = repo.create(JobCreate(source_filename="safe.txt", source_path="dirty/safe.txt",
        source_hash="a" * 64, model="test", policy_name="default", policy_version=1))
    repo.update(row.id, JobStatus.PROCESSING)
    assert repo.recover_interrupted() == 1
    recovered = repo.get(row.id)
    assert recovered is not None and recovered.status == "interrupted"
    assert repo.eligible_retries()[0].id == row.id
