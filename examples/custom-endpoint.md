# Custom endpoint

Use custom mode for an authenticated TLS reverse proxy, internal DNS name, path, or
alternate port.

```env
OLLAMA_CONNECTION_MODE=custom
OLLAMA_BASE_URL=https://ollama.internal.example:8443/ollama
OLLAMA_MODEL=gemma3:4b
CLEANROOM_ALLOW_PUBLIC_OLLAMA=false
CLEANROOM_ALLOW_INSECURE_REMOTE_OLLAMA=false
```

Cleanroom resolves every address, rejects mixed public/private DNS, strips credentials
from display, rejects URL query parameters, and never follows redirects to public IPs.

Expected config output:

```text
Connection Mode: Custom
Endpoint: https://ollama.internal.example:8443/ollama
Model: gemma3:4b
Endpoint Type: Private
```

