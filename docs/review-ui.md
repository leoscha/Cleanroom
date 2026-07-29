# Local review UI

The v0.4 development foundation provides a loopback-only, server-rendered review queue
for quarantined jobs. Start it with:

```bash
cleanroom review
```

Then open `http://127.0.0.1:8765/review`. The command always uses the validated
`CLEANROOM_API_HOST`, which accepts loopback addresses only. Cleanroom does not open a
firewall port, launch a browser, load external assets, or bind to `0.0.0.0`.

## Current foundation

The dashboard shows privacy-safe job metadata, category/source counts, verification
results, PDF structure results, and quarantine reason codes. It does not render source
documents, matched plaintext, replacement mappings, private review diffs, or unknown
report fields. Filenames and every report value are HTML escaped.

Review responses use `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, and
a restrictive Content Security Policy. Requests whose URL host is not loopback are
rejected. The interface has no JavaScript and no external network dependencies.

## Approval state-machine design

Approval actions are intentionally absent from this foundation. v0.4 will not provide
a generic “release anyway” control. The planned transitions are:

```text
quarantined
  ├─ review-only policy finding accepted ─ fresh verification ─ completed
  ├─ policy changed ─ reprocess from unchanged original ─ completed/quarantined
  └─ rejected ─ remains quarantined with an auditable decision
```

An approval may proceed only when deterministic, contextual, placeholder, original
absence, and format-specific structural verification all pass. A failed verification
cannot be overridden through the UI.

Before mutations are enabled, Cleanroom requires:

- a persistent decision record containing job, decision type, timestamp, policy
  version, output hash, and verification result;
- one-time CSRF tokens and POST-only state transitions;
- a workspace lock around verification and file movement;
- a fresh disk reopen and verification immediately before release;
- collision-safe movement from quarantine to `spotless/`;
- tests for replay, stale output, missing files, concurrent decisions, and rollback;
- privacy-safe logs and API responses without reviewer-entered sensitive text.

## Threat boundary

The dashboard assumes a trusted local operator and an uncompromised host. Loopback is
not an authentication system, so the UI must not be exposed through a reverse proxy,
container port publication, SSH forwarding shared with untrusted users, or a browser
running untrusted local extensions. Multi-user authentication and authorization remain
out of scope for v0.4.
