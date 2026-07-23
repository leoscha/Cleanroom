# Tailscale Ollama

Ollama has no built-in authentication by default. Restrict the server with Tailscale
ACLs and host firewall rules; never expose port 11434 publicly. Cleanroom does not
change firewall rules or configure Ollama's listen address.

Run `cleanroom configure ollama`, choose **Private-network Ollama**, enter the server's
literal Tailscale address, and explicitly confirm HTTP only when the trusted Tailscale
transport is acceptable.

```env
OLLAMA_CONNECTION_MODE=private-network
OLLAMA_BASE_URL=http://100.100.10.20:11434
OLLAMA_MODEL=gemma3:4b
CLEANROOM_ALLOW_INSECURE_REMOTE_OLLAMA=true
```

Expected doctor classification:

```text
✓ Connection mode: Private Network
✓ Endpoint classification: Tailscale
✓ Host validated
```

