import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from cleanroom.config.policies import PolicyError, load_policy
from cleanroom.config.settings import Settings
from cleanroom.files.discovery import discover_files
from cleanroom.files.lifecycle import atomic_write_text, collision_safe
from cleanroom.files.text_handler import (
    FileSafetyError,
    file_hash,
    read_utf8,
    validate_input,
    wait_until_stable,
)


def test_settings_reject_public_ollama() -> None:
    with pytest.raises(ValidationError, match="Public Ollama"):
        Settings(OLLAMA_CONNECTION_MODE="custom", OLLAMA_BASE_URL="https://8.8.8.8:11434")


def test_settings_accept_tailscale() -> None:
    settings = Settings(OLLAMA_CONNECTION_MODE="private-network",
                        OLLAMA_BASE_URL="http://100.100.1.2:11434",
                        CLEANROOM_ALLOW_INSECURE_REMOTE_OLLAMA=True)
    assert settings.ollama_base_url.startswith("http")


def test_pdf_settings_and_extensions_are_validated() -> None:
    settings = Settings(OLLAMA_BASE_URL="http://127.0.0.1:11434",
                        CLEANROOM_SUPPORTED_EXTENSIONS=".PDF,.txt",
                        CLEANROOM_PDF_REPLACEMENT_MODE="blank")
    assert settings.extension_set == {".pdf", ".txt"}
    assert settings.pdf_reject_images is True
    with pytest.raises(ValidationError, match="PDF_REPLACEMENT_MODE"):
        Settings(OLLAMA_BASE_URL="http://127.0.0.1:11434",
                 CLEANROOM_PDF_REPLACEMENT_MODE="overlay")
    with pytest.raises(ValidationError, match="SUPPORTED_EXTENSIONS"):
        Settings(OLLAMA_BASE_URL="http://127.0.0.1:11434",
                 CLEANROOM_SUPPORTED_EXTENSIONS=".txt,.docx")


def test_policy_parsing_and_unknown_values(tmp_path: Path) -> None:
    assert load_policy(Path("config/default-policy.yaml")).name == "default"
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: bad\nversion: 1\nminimum_confidence: 1\nactions: {BOGUS: replace}\nplaceholders: {}")
    with pytest.raises(PolicyError):
        load_policy(bad)


def test_discovery_filters_hidden_temp_links_and_formats(tmp_path: Path) -> None:
    good = tmp_path / "good.txt"
    good.write_text("ok")
    (tmp_path / ".hidden.txt").write_text("x")
    (tmp_path / "draft.tmp").write_text("x")
    (tmp_path / "data.pdf").write_text("x")
    (tmp_path / "linked.txt").symlink_to(good)
    assert discover_files(tmp_path) == [good]
    assert discover_files(tmp_path, {".txt", ".pdf"}) == [tmp_path / "data.pdf", good]


def test_file_safety_utf8_size_path_hash_and_stability(tmp_path: Path) -> None:
    dirty = tmp_path / "dirty"
    dirty.mkdir()
    file = dirty / "x.txt"
    file.write_text("hello", encoding="utf-8")
    assert validate_input(file, dirty, 5) == file.resolve()
    assert file_hash(file) == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    asyncio.run(wait_until_stable(file, 0))
    with pytest.raises(FileSafetyError, match="maximum"):
        validate_input(file, dirty, 4)
    with pytest.raises(FileSafetyError, match="outside"):
        validate_input(tmp_path / "other.txt", dirty, 100)
    link = dirty / "link.txt"
    link.symlink_to(file)
    with pytest.raises(FileSafetyError, match="symlink"):
        validate_input(link, dirty, 100)
    bad = dirty / "bad.txt"
    bad.write_bytes(b"\xff")
    with pytest.raises(FileSafetyError, match="UTF-8"):
        read_utf8(bad)


def test_stability_detects_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    file = tmp_path / "x.txt"
    file.write_text("a")

    async def mutate(_: float) -> None:
        file.write_text("changed")

    monkeypatch.setattr(asyncio, "sleep", mutate)
    with pytest.raises(FileSafetyError, match="copied"):
        asyncio.run(wait_until_stable(file, 1))


def test_collision_and_atomic_write(tmp_path: Path) -> None:
    first = atomic_write_text(tmp_path, "out.txt", "one")
    second = atomic_write_text(tmp_path, "out.txt", "two")
    assert first.read_text() == "one"
    assert second.name == "out-2.txt" and second.read_text() == "two"
    assert collision_safe(tmp_path, "out.txt").name == "out-3.txt"
    assert not list(tmp_path.glob(".cleanroom-*"))
