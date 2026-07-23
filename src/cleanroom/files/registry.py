from pathlib import Path
from typing import Any

from cleanroom.files.base import DocumentHandler


class UnsupportedExtensionError(ValueError):
    pass


class DocumentHandlerRegistry:
    def __init__(self, handlers: list[DocumentHandler[Any, Any]]) -> None:
        self._handlers: dict[str, DocumentHandler[Any, Any]] = {}
        for handler in handlers:
            for extension in handler.supported_extensions:
                normalized = extension.lower()
                if normalized in self._handlers:
                    raise ValueError(f"duplicate document handler for {normalized}")
                self._handlers[normalized] = handler

    @property
    def supported_extensions(self) -> set[str]:
        return set(self._handlers)

    def for_path(self, path: Path) -> DocumentHandler[Any, Any]:
        try:
            return self._handlers[path.suffix.lower()]
        except KeyError as exc:
            raise UnsupportedExtensionError(
                f"unsupported document extension: {path.suffix.lower() or '<none>'}"
            ) from exc
