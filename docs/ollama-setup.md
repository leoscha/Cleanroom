# Ollama connection setup

## Local (recommended)

Install Ollama, install a model, and run Cleanroom. A new workspace already contains:

```env
OLLAMA_CONNECTION_MODE=local
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=gemma3:4b
```

```bash
ollama pull gemma3:4b
cleanroom doctor
```

Local mode accepts only `127.0.0.1`, `localhost`, and `::1` endpoints.

## Private network (LAN, VPN, or Tailscale)

Run `cleanroom configure ollama` and select **Private-network Ollama**. Cleanroom
requires an RFC1918, private IPv6, or Tailscale (`100.64.0.0/10`) address and checks
every resolved IP. Public or mixed public/private DNS results are rejected.

Ollama does not provide authentication by default. Remote plain HTTP is unencrypted
and requires explicit confirmation in the wizard, which writes:

```env
OLLAMA_CONNECTION_MODE=private-network
OLLAMA_BASE_URL=http://100.100.1.2:11434
CLEANROOM_ALLOW_INSECURE_REMOTE_OLLAMA=true
```

Install Ollama and the configured model on the Windows host. To listen on all local
interfaces for the current PowerShell session:

```powershell
$env:OLLAMA_HOST="0.0.0.0:11434"; ollama serve
ollama pull gemma3:4b
```

Listening on all interfaces is safe only with Windows Firewall restricted to the
private/Tailscale profile and Tailscale ACLs limited to the Cleanroom client. Never
forward port 11434, expose it publicly, or use a public reverse proxy.

Set the literal Tailscale IPv4 address in `.env` or use the wizard, run
`cleanroom doctor`, and confirm the checklist reports Private Network, Tailscale,
a reachable model, and structured output support.

## Custom

Custom mode supports secured reverse proxies, internal DNS, containers, paths, and
alternate ports. Use HTTPS for remote endpoints. Credentials in URLs are masked in
CLI output, but query parameters and fragments are rejected so secrets cannot leak
through logs or malformed provider paths. Cleanroom revalidates redirects before
following them and never follows a redirect to a public endpoint.

```env
OLLAMA_CONNECTION_MODE=custom
OLLAMA_BASE_URL=https://ollama.internal:8443/proxy
```

## Migrating an existing remote configuration

Existing `.env` files that contain a remote `OLLAMA_BASE_URL` must explicitly select
a mode. Add:

```env
OLLAMA_CONNECTION_MODE=private-network
```

If that remote endpoint uses plain HTTP, also acknowledge transport risk with
`CLEANROOM_ALLOW_INSECURE_REMOTE_OLLAMA=true`. Cleanroom reports the migration and
does not rewrite existing configuration automatically.
