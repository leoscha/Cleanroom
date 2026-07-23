import asyncio
import os
from pathlib import Path

from watchdog.events import (
    DirCreatedEvent,
    DirMovedEvent,
    FileCreatedEvent,
    FileMovedEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from cleanroom.services.processing_service import DuplicateFileError, ProcessingService


class _Handler(FileSystemEventHandler):
    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue[Path]) -> None:
        self.loop, self.queue = loop, queue

    def on_created(self, event: DirCreatedEvent | FileCreatedEvent) -> None:
        if not event.is_directory:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, Path(os.fsdecode(event.src_path)))

    def on_moved(self, event: DirMovedEvent | FileMovedEvent) -> None:
        if not event.is_directory:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, Path(os.fsdecode(event.dest_path)))


async def watch_folder(directory: Path, service: ProcessingService) -> None:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Path] = asyncio.Queue()
    observer = Observer()
    observer.schedule(_Handler(loop, queue), str(directory), recursive=False)
    observer.start()
    try:
        while True:
            path = await queue.get()
            try:
                await service.process(path)
            except (ValueError, OSError, DuplicateFileError):
                continue
    finally:
        observer.stop()
        observer.join()
