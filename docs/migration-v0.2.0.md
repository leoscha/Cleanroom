# Migration notes for v0.2.0

v0.2.0 makes Ollama deployment intent explicit. Cleanroom does not rewrite existing
`.env` files.

## Local Ollama

No change is required if Ollama uses `http://127.0.0.1:11434`. You may add the mode
for clarity:

```env
OLLAMA_CONNECTION_MODE=local
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

## Existing LAN, VPN, or Tailscale endpoint

An old configuration containing only a remote `OLLAMA_BASE_URL` now stops with a
migration message. Add:

```env
OLLAMA_CONNECTION_MODE=private-network
```

If the endpoint uses unencrypted HTTP, also add:

```env
CLEANROOM_ALLOW_INSECURE_REMOTE_OLLAMA=true
```

Ollama has no built-in authentication by default. Use a trusted encrypted network,
strict network controls, or an authenticated HTTPS reverse proxy.

## Custom endpoints

Reverse proxies, internal DNS, paths, and alternate ports should use:

```env
OLLAMA_CONNECTION_MODE=custom
OLLAMA_BASE_URL=https://ollama.internal:8443/proxy
```

Run `cleanroom configure ollama` for guided validation, then `cleanroom doctor`.
Public endpoints are never enabled automatically.

