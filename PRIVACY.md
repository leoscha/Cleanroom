# Privacy

Document text is read locally and sent only to the configured Ollama HTTP endpoint.
No cloud inference provider exists. Verify that the endpoint belongs to your
loopback, RFC1918, or Tailscale network before processing real material.

In memory, Cleanroom retains source text, exact findings, replacement mappings, and
chunks only for the active job. Persistent reports contain filenames, hashes,
categories, counts, confidence, sources, timing, and safe diagnostics—not matched
values. SQLite contains job metadata and paths, never document bodies or findings.

For PDFs, in-memory state also includes page text, glyph bounding boxes, normalized
character maps, and redaction rectangles. Reports retain only counts, mapping status,
structural flags, and warnings. PDF title, author, subject, keywords, dates, creator,
producer, XML metadata, comment text, form values, attachment names, and extracted
document text are never copied into reports, logs, or SQLite.

`CLEANROOM_WRITE_REVIEW_DIFF=true` is a development-only exception: files under
`reports/private-review/` can contain original plaintext. The directory is ignored
by Git. Secure and delete those artifacts according to your retention policy.
