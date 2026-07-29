# Product philosophy

Cleanroom is a local-first AI Privacy Gateway that sanitizes sensitive information
before documents are shared with AI systems.

## Why local-first

Privacy tooling should not create a new disclosure channel. Files, findings, prompts,
and model responses stay on the operator's machine or travel only to an explicitly
configured private Ollama deployment. Local inference is the default; remote inference
requires deliberate configuration.

## Why verification matters

Detection is only the beginning. Cleanroom verifies that replaced source values are
gone, parses generated placeholders, rescans content outside placeholders, and can use
a separate model verification pass. Uncertainty is reported instead of being treated
as success.

## Why policies exist

Context and risk tolerance differ. Versioned policies make category thresholds,
replacement behavior, and review requirements visible and reviewable instead of
hiding them in code or prompts.

## Why Cleanroom fails closed

A polished-looking file is dangerous if sanitization was incomplete. Unsupported
input, unsafe endpoints, malformed model output, unresolved review findings, mapping
uncertainty, or failed verification stops release and routes output to quarantine.

## Why placeholders beat deletion

Deletion can destroy meaning and make a document hard to use. Stable placeholders
retain grammatical and operational context, show what kind of information was
removed, and consistently represent repeated entities without retaining their value.

## Threat model

Cleanroom addresses accidental disclosure of sensitive text to downstream AI systems.
It assumes the local machine, workspace permissions, chosen Ollama host, and operator
are trusted. It minimizes ordinary logs and reports, rejects public inference by
default, validates every resolved endpoint address, and avoids exposing matched
plaintext in normal metadata.

It does not defend a compromised host, malicious model server, privileged local user,
unsafe optional private-review diff, or every forensic recovery technique.

## Non-guarantees and current limitations

- Detection reduces risk; deterministic rules have boundaries and AI detection is
  probabilistic.
- Human review may still be required, especially for high-risk or ambiguous content.
- OCR and image sanitization are unsupported. PDFs containing images fail closed by
  default unless an operator explicitly accepts responsibility for reviewed pixels.
- Scans, images, DOCX, spreadsheets, and other unsupported formats are rejected rather
  than silently processed.
- Supported PDFs must be digitally generated and text based. Passing verification is
  not a guarantee of forensic irrecoverability against every PDF parser.
- Processing is sequential and designed for one local workspace, not multi-user use.
- Public or untrusted inference can expose content; local Ollama is recommended.
