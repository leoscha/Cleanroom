from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import SplitResult, urljoin, urlsplit, urlunsplit


class EndpointValidationError(ValueError):
    """Raised when an Ollama endpoint is unsafe or incompatible with its mode."""


class ConnectionMode(StrEnum):
    LOCAL = "local"
    PRIVATE_NETWORK = "private-network"
    CUSTOM = "custom"

    @property
    def display_name(self) -> str:
        return self.value.replace("-", " ").title()


class EndpointKind(StrEnum):
    LOOPBACK = "loopback"
    PRIVATE = "private"
    TAILSCALE = "tailscale"
    PUBLIC = "public"

    @property
    def display_name(self) -> str:
        return self.value.title()


Resolver = Callable[[str, int], set[ipaddress.IPv4Address | ipaddress.IPv6Address]]


@dataclass(frozen=True)
class ValidatedEndpoint:
    url: str
    safe_url: str
    mode: ConnectionMode
    kind: EndpointKind
    addresses: tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]
    allow_public: bool = False
    allow_insecure_remote: bool = False


def validate_ollama_endpoint(
    url: str,
    mode: ConnectionMode | str,
    *,
    allow_public: bool = False,
    allow_insecure_remote: bool = False,
    resolver: Resolver | None = None,
) -> ValidatedEndpoint:
    try:
        connection_mode = ConnectionMode(mode)
    except ValueError as exc:
        choices = ", ".join(item.value for item in ConnectionMode)
        raise EndpointValidationError(
            f"Invalid OLLAMA_CONNECTION_MODE; choose one of: {choices}"
        ) from exc

    parsed = _parse_url(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = (resolver or resolve_host)(parsed.hostname or "", port)
    if not addresses:
        raise EndpointValidationError("Ollama endpoint DNS resolution returned no addresses")

    kinds = {_address_kind(address) for address in addresses}
    if EndpointKind.PUBLIC in kinds and len(kinds) > 1:
        raise EndpointValidationError(
            "Ollama endpoint has mixed public/private DNS resolution; all resolved IPs must be safe"
        )
    if EndpointKind.PUBLIC in kinds and not allow_public:
        raise EndpointValidationError(
            "Public Ollama endpoints are blocked; set CLEANROOM_ALLOW_PUBLIC_OLLAMA=true "
            "only if you explicitly accept the risk"
        )
    if connection_mode is ConnectionMode.LOCAL and kinds != {EndpointKind.LOOPBACK}:
        if url != "http://127.0.0.1:11434":
            raise EndpointValidationError(
                "A remote Ollama endpoint is configured.\n\n"
                "Please add:\n\nOLLAMA_CONNECTION_MODE=private-network\n\n"
                "to continue using this deployment."
            )
        raise EndpointValidationError("Local mode only accepts loopback Ollama endpoints")
    if connection_mode is ConnectionMode.PRIVATE_NETWORK:
        allowed = {EndpointKind.PRIVATE, EndpointKind.TAILSCALE}
        if not kinds <= allowed:
            raise EndpointValidationError(
                "Private-network mode only accepts RFC1918, private IPv6, or Tailscale endpoints"
            )
    remote = kinds != {EndpointKind.LOOPBACK}
    if remote and parsed.scheme == "http" and not allow_insecure_remote:
        raise EndpointValidationError(
            "Remote Ollama over HTTP is unencrypted; set "
            "CLEANROOM_ALLOW_INSECURE_REMOTE_OLLAMA=true only on a trusted network"
        )

    kind = _combined_kind(kinds)
    normalized = urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
    return ValidatedEndpoint(
        url=normalized,
        safe_url=format_safe_endpoint(normalized),
        mode=connection_mode,
        kind=kind,
        addresses=tuple(sorted(addresses, key=lambda item: (item.version, int(item)))),
        allow_public=allow_public,
        allow_insecure_remote=allow_insecure_remote,
    )


def validate_redirect(
    endpoint: ValidatedEndpoint,
    location: str,
    *,
    allow_insecure_remote: bool = False,
    resolver: Resolver | None = None,
) -> ValidatedEndpoint:
    target = urljoin(f"{endpoint.url}/", location)
    return validate_ollama_endpoint(
        target,
        endpoint.mode,
        allow_public=False,
        allow_insecure_remote=allow_insecure_remote or endpoint.allow_insecure_remote,
        resolver=resolver,
    )


def resolve_host(host: str, port: int) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        return {ipaddress.ip_address(host)}
    except ValueError:
        pass
    try:
        return {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, port)}
    except OSError as exc:
        raise EndpointValidationError(f"Could not resolve Ollama endpoint host: {host}") from exc


def format_safe_endpoint(url: str) -> str:
    """Remove credentials and URL parameters while retaining useful endpoint details."""
    parsed = urlsplit(url)
    hostname = parsed.hostname or "invalid-host"
    display_host = f"[{hostname}]" if ":" in hostname else hostname
    if parsed.username is not None or parsed.password is not None:
        display_host = f"***@{display_host}"
    port = f":{parsed.port}" if parsed.port is not None else ""
    return urlunsplit((parsed.scheme, f"{display_host}{port}", parsed.path.rstrip("/"), "", ""))


def _parse_url(url: str) -> SplitResult:
    try:
        parsed = urlsplit(url.strip())
        _ = parsed.port
    except ValueError as exc:
        raise EndpointValidationError("OLLAMA_BASE_URL contains an invalid host or port") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise EndpointValidationError("OLLAMA_BASE_URL must be an http(s) URL with a host")
    if parsed.fragment or parsed.query:
        raise EndpointValidationError("OLLAMA_BASE_URL must not contain query parameters or fragments")
    if any(character.isspace() for character in url):
        raise EndpointValidationError("OLLAMA_BASE_URL must not contain whitespace")
    return parsed


def _address_kind(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> EndpointKind:
    if address.is_loopback:
        return EndpointKind.LOOPBACK
    if isinstance(address, ipaddress.IPv4Address):
        if address in ipaddress.ip_network("100.64.0.0/10"):
            return EndpointKind.TAILSCALE
        if any(address in network for network in (
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
            ipaddress.ip_network("192.168.0.0/16"),
        )):
            return EndpointKind.PRIVATE
    elif address in ipaddress.ip_network("fc00::/7") or address.is_link_local:
        return EndpointKind.PRIVATE
    return EndpointKind.PUBLIC


def _combined_kind(kinds: set[EndpointKind]) -> EndpointKind:
    if EndpointKind.PUBLIC in kinds:
        return EndpointKind.PUBLIC
    if EndpointKind.TAILSCALE in kinds:
        return EndpointKind.TAILSCALE
    if EndpointKind.PRIVATE in kinds:
        return EndpointKind.PRIVATE
    return EndpointKind.LOOPBACK
