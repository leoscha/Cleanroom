# Local Ollama

Local inference is recommended and requires no network exposure.

```bash
ollama pull gemma3:4b
cleanroom init
cleanroom doctor
```

Generated `.env` values:

```env
OLLAMA_CONNECTION_MODE=local
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=gemma3:4b
```

Expected readiness excerpt:

```text
Ollama
✓ Connection mode: Local
✓ Endpoint: http://127.0.0.1:11434
✓ Endpoint classification: Loopback
✓ Ollama reachable
✓ Model installed: gemma3:4b
✓ Structured output supported
```

