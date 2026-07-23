# Text-based PDF support

Cleanroom supports digitally generated PDFs whose text can be extracted by PyMuPDF.
It does not perform OCR. Image-only and likely scanned documents are quarantined with
`LIKELY_SCANNED_PDF`; use `cleanroom inspect dirty/example.pdf` to check a file without
printing its text.

> Cleanroom verifies that redacted values are absent from supported extraction paths,
> but this MVP does not claim forensic sanitization against every possible PDF
> recovery technique.

## Extraction and mapping

The PDF handler records pages, blocks, lines, spans, glyph bounding boxes, and global
offsets. It normalizes Unicode and ligatures, nonbreaking and repeated spaces, line
breaks, and hyphenated line wraps while retaining a source reference for every
normalized character. Findings from the shared regex and Ollama pipeline are accepted
only when their offsets still match the normalized text.

Each non-whitespace finding character must map back to source glyph geometry. Findings
may cross spans and lines and may repeat on one or more pages. Cleanroom produces the
smallest practical rectangle per source span and merges only adjacent rectangles on
the same line. Mapping below `CLEANROOM_PDF_MAPPING_MIN_CONFIDENCE` fails closed; no
PDF is released.

## Real redaction and replacement modes

Cleanroom uses PyMuPDF redaction annotations and applies them so underlying text is
removed. Drawing a rectangle alone is never considered redaction. It then performs a
fresh, non-incremental save with full garbage collection.

- `label` inserts the policy placeholder when it safely fits. If it cannot fit, an
  opaque redaction is used and the report records a fallback.
- `black_box` removes the text and leaves an opaque box.
- `blank` removes the text without a visible box.

Set `CLEANROOM_PDF_REPLACEMENT_MODE`; the default is `label`. Layout is not reflowed,
so a placeholder can occupy only the mapped area.

## Metadata and active content

By default Cleanroom clears standard and XML metadata, deletes annotations, removes
links and attachments during scrubbing, and resets fields. Inputs with forms,
embedded files, JavaScript, launch/external actions, or optional-content layers are
rejected before document content is sent to Ollama. Encrypted and password-protected
PDFs are unsupported. Cleanroom never executes actions or extracts attachments.

## Verification

The saved output is reopened from disk. Cleanroom checks page count, encryption,
metadata, attachments, forms, annotations, JavaScript/actions, and optional content.
It confirms accepted values are absent from normal extraction, reconstructed raw text
dictionaries, and metadata. The shared placeholder-aware deterministic and optional
Ollama verification pipeline then scans the sanitized extracted text.

A failure at any step sends the output to quarantine or stops before release. Reports
contain only safe counts, structure flags, hashes, mapping warnings, and reason codes.

## Current limitations

- No OCR or sanitization of pixels in scanned pages.
- Complex encodings, damaged font maps, unusual writing directions, or ambiguous
  geometry may be quarantined.
- Replacement labels do not reflow surrounding PDF layout.
- Unsupported active content is rejected rather than transformed.
- Verification covers documented extraction paths and does not prove resistance to
  every low-level or forensic PDF recovery technique.

OCR and raster-aware handling are planned as a separate milestone; no OCR dependency
is included in this release.
