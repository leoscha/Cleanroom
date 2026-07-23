import asyncio
import ipaddress
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from cleanroom.cli import commands
from cleanroom.config.ollama_endpoint import (
    EndpointKind,
    EndpointValidationError,
    format_safe_endpoint,
    validate_ollama_endpoint,
    validate_redirect,
)
from cleanroom.config.settings import Settings
from cleanroom.providers.ollama import OllamaDetectionProvider

runner = CliRunner()


def addresses(*values: str):
    resolved = {ipaddress.ip_address(value) for value in values}
    return lambda _host, _port: resolved


def test_local_defaults_and_loopback_variants() -> None:
    settings = Settings(_env_file=None)
    assert settings.ollama_connection_mode.value == "local"
    assert settings.ollama_base_url == "http://127.0.0.1:11434"
    for url in ("http://127.0.0.1:11434", "http://[::1]:11434"):
        assert validate_ollama_endpoint(url, "local").kind is EndpointKind.LOOPBACK
    assert validate_ollama_endpoint(
        "http://localhost:11434", "local", resolver=addresses("127.0.0.1", "::1")
    ).kind is EndpointKind.LOOPBACK


@pytest.mark.parametrize("url", [
    "http://192.168.1.20:11434",
    "http://100.100.1.2:11434",
])
def test_local_mode_rejects_remote_and_gives_migration(url: str) -> None:
    with pytest.raises(EndpointValidationError, match="OLLAMA_CONNECTION_MODE=private-network"):
        validate_ollama_endpoint(url, "local")


@pytest.mark.parametrize("url,kind", [
    ("http://10.0.0.15:11434", EndpointKind.PRIVATE),
    ("http://172.16.2.3:11434", EndpointKind.PRIVATE),
    ("http://192.168.1.20:11434", EndpointKind.PRIVATE),
    ("http://100.100.1.2:11434", EndpointKind.TAILSCALE),
    ("http://[fd00::20]:11434", EndpointKind.PRIVATE),
])
def test_private_network_ranges(url: str, kind: EndpointKind) -> None:
    endpoint = validate_ollama_endpoint(
        url, "private-network", allow_insecure_remote=True
    )
    assert endpoint.kind is kind


def test_private_network_requires_explicit_insecure_http_override() -> None:
    with pytest.raises(EndpointValidationError, match="ALLOW_INSECURE_REMOTE"):
        validate_ollama_endpoint("http://10.0.0.15:11434", "private-network")


def test_public_custom_endpoint_is_opt_in_and_secure() -> None:
    with pytest.raises(EndpointValidationError, match="Public Ollama endpoints are blocked"):
        validate_ollama_endpoint("https://8.8.8.8:11434", "custom")
    endpoint = validate_ollama_endpoint(
        "https://8.8.8.8:11434", "custom", allow_public=True
    )
    assert endpoint.kind is EndpointKind.PUBLIC


def test_custom_internal_dns_and_mixed_dns_validation() -> None:
    endpoint = validate_ollama_endpoint(
        "https://ollama.internal:8443/proxy", "custom",
        resolver=addresses("10.0.0.2")
    )
    assert endpoint.kind is EndpointKind.PRIVATE
    with pytest.raises(EndpointValidationError, match="mixed public/private"):
        validate_ollama_endpoint(
            "https://ollama.internal:8443", "custom", allow_public=True,
            resolver=addresses("10.0.0.2", "8.8.8.8")
        )


def test_redirects_are_revalidated() -> None:
    endpoint = validate_ollama_endpoint("http://127.0.0.1:11434", "local")
    relative = validate_redirect(endpoint, "/api/tags")
    assert relative.url == "http://127.0.0.1:11434/api/tags"
    with pytest.raises(EndpointValidationError, match="Public Ollama endpoints are blocked"):
        validate_redirect(endpoint, "https://8.8.8.8/api/tags")
    public = validate_ollama_endpoint(
        "https://8.8.8.8:11434", "custom", allow_public=True
    )
    with pytest.raises(EndpointValidationError, match="Public Ollama endpoints are blocked"):
        validate_redirect(public, "/api/tags")


def test_provider_does_not_follow_redirect_to_public_endpoint() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(302, headers={"location": "https://8.8.8.8/api/tags"})

    endpoint = validate_ollama_endpoint("http://127.0.0.1:11434", "local")
    provider = OllamaDetectionProvider(
        endpoint, "test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    health = asyncio.run(provider.health())
    assert health["reachable"] is False
    assert len(requests) == 1


def test_safe_endpoint_format_masks_credentials_and_parameters() -> None:
    assert format_safe_endpoint(
        "https://user:secret@ollama.internal:8443/proxy?token=secret#x"
    ) == "https://***@ollama.internal:8443/proxy"


def test_existing_remote_settings_require_migration() -> None:
    with pytest.raises(ValidationError, match="OLLAMA_CONNECTION_MODE=private-network"):
        Settings(_env_file=None, OLLAMA_BASE_URL="http://100.100.1.2:11434")


def test_init_writes_local_ollama_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(commands.app, ["init"])
    assert result.exit_code == 0
    env = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "OLLAMA_CONNECTION_MODE=local" in env
    assert "OLLAMA_BASE_URL=http://127.0.0.1:11434" in env
    assert "local Ollama instance" in result.stdout


def test_configure_local_preserves_other_env_settings(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "KEEP_ME=yes\nOLLAMA_BASE_URL=http://100.100.1.2:11434\n", encoding="utf-8"
    )
    result = runner.invoke(
        commands.app, ["configure", "ollama"], input="1\n\n"
    )
    assert result.exit_code == 0
    env = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "KEEP_ME=yes" in env
    assert "OLLAMA_CONNECTION_MODE=local" in env
    assert "OLLAMA_BASE_URL=http://127.0.0.1:11434" in env


def test_configure_private_requires_http_confirmation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        commands.app, ["configure", "ollama"],
        input="2\nhttp://192.168.1.20:11434\ny\n",
    )
    assert result.exit_code == 0
    env = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "OLLAMA_CONNECTION_MODE=private-network" in env
    assert "CLEANROOM_ALLOW_INSECURE_REMOTE_OLLAMA=true" in env
