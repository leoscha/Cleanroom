# Private Ollama setup

Install Ollama and the configured model on the Windows host. To listen on all local
interfaces for the current PowerShell session:

```powershell
$env:OLLAMA_HOST="0.0.0.0:11434"; ollama serve
ollama pull gemma3:4b
```

Listening on all interfaces is safe only with Windows Firewall restricted to the
private/Tailscale profile and Tailscale ACLs limited to the Cleanroom client. Never
forward port 11434, expose it publicly, or use a public reverse proxy.

Set the literal Tailscale IPv4 address in `.env`, run `cleanroom doctor`, and
confirm the checklist reports a Tailscale endpoint, reachable model, and structured
output support.
