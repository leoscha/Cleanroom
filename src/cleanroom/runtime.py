from dataclasses import dataclass

from cleanroom.config.policies import load_policy
from cleanroom.config.settings import Settings
from cleanroom.database.repository import JobRepository
from cleanroom.database.session import create_db_engine, initialize_database, session_factory
from cleanroom.files.manifest import clean_manifests
from cleanroom.files.workspace_lock import WorkspaceBusyError, WorkspaceLock
from cleanroom.providers.ollama import OllamaDetectionProvider
from cleanroom.services.processing_service import ProcessingService
from cleanroom.services.scan_service import ScanService


@dataclass
class Runtime:
    settings: Settings
    repository: JobRepository
    provider: OllamaDetectionProvider
    processing: ProcessingService
    scanning: ScanService


def build_runtime(settings: Settings | None = None) -> Runtime:
    current = settings or Settings()
    policy = load_policy(current.policy_path)
    engine = create_db_engine(current.database_url)
    initialize_database(engine)
    repository = JobRepository(session_factory(engine))
    try:
        with WorkspaceLock(current.temp_dir.parent / "workspace.lock"):
            repository.recover_interrupted()
            clean_manifests(current.temp_dir)
    except WorkspaceBusyError:
        pass
    provider = OllamaDetectionProvider(current.validated_ollama_endpoint, current.ollama_model,
                                       current.ollama_timeout_seconds, current.ollama_max_retries)
    processing = ProcessingService(current, policy, repository, provider)
    return Runtime(current, repository, provider, processing,
                   ScanService(processing, current.dirty_dir, current.extension_set))
