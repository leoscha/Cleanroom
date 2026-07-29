from dataclasses import replace
from pathlib import Path

import pymupdf as fitz
import pytest
from reportlab.pdfgen import canvas

from cleanroom.files.pdf_handler import (
    PdfDocumentHandler,
    PdfEncryptedError,
    PdfMalformedError,
    PdfMappingError,
    PdfUnsupportedError,
    create_synthetic_pdf,
)
from cleanroom.files.registry import DocumentHandlerRegistry, UnsupportedExtensionError
from cleanroom.files.text_handler import TextDocumentHandler
from cleanroom.models.finding import Category, Finding


def make_pdf(path: Path, pages: list[list[tuple[tuple[float, float], str]]],
             metadata: dict[str, str] | None = None) -> None:
    document = fitz.open()  # type: ignore[no-untyped-call]
    try:
        for lines in pages:
            page = document.new_page()
            for point, text in lines:
                page.insert_text(point, text, fontsize=12)
        if metadata:
            document.set_metadata(metadata)
        document.save(path)  # type: ignore[no-untyped-call]
    finally:
        document.close()  # type: ignore[no-untyped-call]


def finding(text: str, source: str, category: Category = Category.PERSON_NAME) -> Finding:
    start = source.index(text)
    return Finding(text=text, category=category, confidence=1, source="test",
                   start=start, end=start + len(text), reason="synthetic test")


def test_registry_selects_real_pdf_handler(settings, policy, tmp_path: Path) -> None:
    pdf = PdfDocumentHandler(policy, settings)
    registry = DocumentHandlerRegistry([TextDocumentHandler(policy), pdf])
    assert registry.for_path(tmp_path / "sample.PDF") is pdf
    with pytest.raises(UnsupportedExtensionError):
        registry.for_path(tmp_path / "sample.docx")


def test_extracts_pages_spans_and_global_offsets(settings, policy, tmp_path: Path) -> None:
    source = tmp_path / "multipage.pdf"
    make_pdf(source, [[((72, 72), "Synthetic Alpha Record with text")],
                      [((72, 72), "Synthetic Beta Record with text")]])
    document = PdfDocumentHandler(policy, settings).extract(source)
    assert document.page_count == 2
    assert "Synthetic Alpha Record" in document.page_text[0]
    assert "Synthetic Beta Record" in document.page_text[1]
    assert "\n\f\n" in document.text
    assert len(document.char_map) == len(document.text)
    for span in document.spans:
        assert span.global_start < span.global_end
        assert span.bbox[2] > span.bbox[0]


def test_normalizes_whitespace_and_hyphenated_line_breaks(
    settings, policy, tmp_path: Path
) -> None:
    source = tmp_path / "normalization.pdf"
    make_pdf(source, [[((72, 72), "Private   customer identi-"),
                       ((72, 90), "fier beside refinery")]])
    extracted = PdfDocumentHandler(policy, settings).extract(source)
    assert "Private customer identifier beside refinery" in extracted.text
    target = finding("customer identifier", extracted.text)
    sanitized = PdfDocumentHandler(policy, settings).sanitize(extracted, [target])
    assert len(sanitized.mappings[0].rectangles) >= 2
    assert sanitized.mappings[0].confidence == 1


def test_maps_repeated_and_multispan_findings(settings, policy, tmp_path: Path) -> None:
    source = tmp_path / "repeated.pdf"
    make_pdf(source, [[((72, 72), "Jane "), ((102, 72), "Example works here."),
                       ((72, 94), "Jane Example returned.")]])
    handler = PdfDocumentHandler(policy, settings)
    extracted = handler.extract(source)
    occurrences = []
    offset = 0
    while (start := extracted.text.find("Jane Example", offset)) >= 0:
        occurrences.append(Finding(text="Jane Example", category=Category.PERSON_NAME,
            confidence=1, source="test", start=start, end=start + 12,
            reason="synthetic name"))
        offset = start + 1
    assert len(occurrences) == 2
    mappings = handler.sanitize(extracted, occurrences).mappings
    assert len(mappings) == 2
    assert mappings[0].placeholder == mappings[1].placeholder == "[PERSON_NAME_1]"


def test_mapping_uncertainty_fails_closed(settings, policy, tmp_path: Path) -> None:
    source = tmp_path / "mapping.pdf"
    make_pdf(source, [[((72, 72), "Jane Example synthetic record")]])
    handler = PdfDocumentHandler(policy, settings)
    extracted = handler.extract(source)
    target = finding("Jane Example", extracted.text)
    broken_map = list(extracted.char_map)
    broken_map[target.start:target.end] = [None] * len(target.text)
    broken = replace(extracted, char_map=tuple(broken_map))
    with pytest.raises(PdfMappingError):
        handler.sanitize(broken, [target])


@pytest.mark.parametrize("mode", ["label", "black_box", "blank"])
def test_real_redaction_removes_text_and_metadata(
    settings, policy, tmp_path: Path, mode: str
) -> None:
    settings.pdf_replacement_mode = mode
    source = tmp_path / f"source-{mode}.pdf"
    output = tmp_path / f"clean-{mode}.pdf"
    secret = "private@example.test"
    make_pdf(source, [[((72, 72), f"Synthetic email: {secret} for testing")]],
             {"title": secret, "author": "Synthetic Author"})
    handler = PdfDocumentHandler(policy, settings)
    extracted = handler.extract(source)
    target = finding(secret, extracted.text, Category.EMAIL)
    sanitized = handler.sanitize(extracted, [target])
    written = handler.write(sanitized, output)
    reopened = handler.extract_output(written)
    structural = handler.verify_output(written, 1)
    assert secret not in reopened.text
    assert secret.encode() not in written.read_bytes()
    assert structural["passed"] is True
    assert structural["metadata_sanitized"] is True
    assert structural["annotations_remaining"] == 0
    if mode == "label":
        assert "[EMAIL_1]" in reopened.text


def test_label_fallback_is_recorded_for_tiny_rectangle(
    settings, policy, tmp_path: Path
) -> None:
    source = tmp_path / "tiny.pdf"
    make_pdf(source, [[((72, 72), "x plus enough synthetic text")]])
    handler = PdfDocumentHandler(policy, settings)
    extracted = handler.extract(source)
    target = finding("x", extracted.text)
    sanitized = handler.sanitize(extracted, [target])
    handler.write(sanitized, tmp_path / "tiny-clean.pdf")
    assert sanitized.write_telemetry["label_fallback_count"] == 1


def test_collision_safe_pdf_output(settings, policy, tmp_path: Path) -> None:
    source = tmp_path / "collision.pdf"
    make_pdf(source, [[((72, 72), "Synthetic clean document with enough text")]])
    handler = PdfDocumentHandler(policy, settings)
    sanitized = handler.sanitize(handler.extract(source), [])
    first = handler.write(sanitized, tmp_path / "result.pdf")
    second = handler.write(sanitized, tmp_path / "result.pdf")
    assert first != second and first.exists() and second.exists()


def test_configured_annotations_are_removed(settings, policy, tmp_path: Path) -> None:
    source = tmp_path / "annotated.pdf"
    make_pdf(source, [[((72, 72), "Synthetic annotated document with enough text")]])
    with fitz.open(source) as document:  # type: ignore[no-untyped-call]
        document[0].add_text_annot((72, 92), "synthetic comment")
        document.save(tmp_path / "annotated-saved.pdf")  # type: ignore[no-untyped-call]
    source = tmp_path / "annotated-saved.pdf"
    handler = PdfDocumentHandler(policy, settings)
    extracted = handler.extract(source)
    assert extracted.inspection is not None
    assert extracted.inspection.annotations_found == 1
    output = handler.write(handler.sanitize(extracted, []), tmp_path / "annotation-clean.pdf")
    assert handler.inspect(output).annotations_found == 0


def test_detects_annotations_forms_embedded_files_and_actions(
    settings, policy, tmp_path: Path
) -> None:
    source = tmp_path / "active.pdf"
    document = fitz.open()  # type: ignore[no-untyped-call]
    try:
        page = document.new_page()
        page.insert_text((72, 72), "Synthetic active PDF with enough text for inspection")
        page.add_text_annot((72, 90), "synthetic comment")
        widget = fitz.Widget()
        widget.field_name = "synthetic-field"
        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        widget.rect = fitz.Rect(72, 110, 220, 130)  # type: ignore[no-untyped-call]
        page.add_widget(widget)
        document.embfile_add("synthetic.txt", b"synthetic", filename="synthetic.txt")
        action = document.get_new_xref()
        document.update_object(action, "<< /S /JavaScript /JS (synthetic) >>")
        page.insert_link({"kind": fitz.LINK_URI,
                          "from": fitz.Rect(72, 140, 200, 155),  # type: ignore[no-untyped-call]
                          "uri": "https://example.invalid"})
        document.save(source)  # type: ignore[no-untyped-call]
    finally:
        document.close()  # type: ignore[no-untyped-call]
    handler = PdfDocumentHandler(policy, settings)
    inspection = handler.inspect(source)
    assert inspection.annotations_found == 1
    assert inspection.forms_found is True
    assert inspection.embedded_files_found == 1
    assert inspection.javascript_found is True
    assert inspection.external_actions_found is True
    assert inspection.supported is False
    with pytest.raises(PdfUnsupportedError):
        handler.extract(source)


def test_image_only_pdf_is_classified_as_scanned(settings, policy, tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    document = fitz.open()  # type: ignore[no-untyped-call]
    try:
        page = document.new_page()
        pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 50, 50), False)
        pixmap.clear_with(240)
        page.insert_image(fitz.Rect(72, 72, 300, 300), pixmap=pixmap)  # type: ignore[no-untyped-call]
        document.save(source)  # type: ignore[no-untyped-call]
    finally:
        document.close()  # type: ignore[no-untyped-call]
    handler = PdfDocumentHandler(policy, settings)
    inspection = handler.inspect(source)
    assert inspection.appears_scanned and "LIKELY_SCANNED_PDF" in inspection.rejection_codes
    assert "PDF_IMAGES_WITHOUT_OCR" in inspection.rejection_codes
    with pytest.raises(PdfUnsupportedError):
        handler.extract(source)


def test_mixed_text_and_images_require_explicit_ocr_risk_override(
    settings, policy, tmp_path: Path
) -> None:
    source = tmp_path / "mixed.pdf"
    document = fitz.open()  # type: ignore[no-untyped-call]
    try:
        page = document.new_page()
        page.insert_text((72, 72), "Synthetic text page with enough extractable content")
        pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 20, 20), False)
        pixmap.clear_with(240)
        page.insert_image(fitz.Rect(72, 100, 150, 180), pixmap=pixmap)  # type: ignore[no-untyped-call]
        document.save(source)  # type: ignore[no-untyped-call]
    finally:
        document.close()  # type: ignore[no-untyped-call]
    handler = PdfDocumentHandler(policy, settings)
    inspection = handler.inspect(source)
    assert not inspection.appears_scanned
    assert "PDF_IMAGES_WITHOUT_OCR" in inspection.rejection_codes
    settings.pdf_reject_images = False
    opted_in = PdfDocumentHandler(policy, settings).inspect(source)
    assert opted_in.supported


@pytest.mark.parametrize("variant,page_count,needle,count", [
    ("multipage", 2, "multi@example.test", 1),
    ("repeated", 1, "repeat@example.test", 2),
])
def test_synthetic_pdf_compatibility_variants(
    settings, policy, tmp_path: Path, variant: str, page_count: int,
    needle: str, count: int,
) -> None:
    source = tmp_path / f"{variant}.pdf"
    create_synthetic_pdf(source, variant)
    extracted = PdfDocumentHandler(policy, settings).extract(source)
    assert extracted.page_count == page_count
    assert extracted.text.count(needle) == count


def test_extracts_and_redacts_reportlab_generated_pdf(
    settings, policy, tmp_path: Path
) -> None:
    source = tmp_path / "reportlab.pdf"
    producer = canvas.Canvas(str(source))
    producer.drawString(72, 720, "Synthetic ReportLab document with enough text")
    producer.drawString(72, 700, "Email: reportlab@example.test")
    producer.showPage()
    producer.save()
    handler = PdfDocumentHandler(policy, settings)
    extracted = handler.extract(source)
    target = finding("reportlab@example.test", extracted.text, Category.EMAIL)
    output = handler.write(handler.sanitize(extracted, [target]), tmp_path / "reportlab-clean.pdf")
    assert handler.verify_output(output, 1)["passed"] is True
    assert handler.verify_original_absence(output, [target])["passed"] is True


def test_rotated_text_mapping_and_redaction(settings, policy, tmp_path: Path) -> None:
    source = tmp_path / "rotated.pdf"
    document = fitz.open()  # type: ignore[no-untyped-call]
    try:
        page = document.new_page()
        page.insert_text((100, 500), "Synthetic rotated@example.test record", rotate=90)
        document.save(source)  # type: ignore[no-untyped-call]
    finally:
        document.close()  # type: ignore[no-untyped-call]
    handler = PdfDocumentHandler(policy, settings)
    extracted = handler.extract(source)
    target = finding("rotated@example.test", extracted.text, Category.EMAIL)
    output = handler.write(handler.sanitize(extracted, [target]), tmp_path / "rotated-clean.pdf")
    assert handler.verify_original_absence(output, [target])["passed"] is True


def test_malformed_and_encrypted_pdfs_fail_closed(settings, policy, tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.pdf"
    malformed.write_bytes(b"not a PDF")
    handler = PdfDocumentHandler(policy, settings)
    with pytest.raises(PdfMalformedError):
        handler.inspect(malformed)

    protected = tmp_path / "protected.pdf"
    document = fitz.open()  # type: ignore[no-untyped-call]
    try:
        page = document.new_page()
        page.insert_text((72, 72), "Synthetic encrypted content")
        document.save(protected, encryption=fitz.PDF_ENCRYPT_AES_256,
                      owner_pw="owner", user_pw="password")  # type: ignore[no-untyped-call]
    finally:
        document.close()  # type: ignore[no-untyped-call]
    assert handler.inspect(protected).encrypted
    with pytest.raises(PdfEncryptedError):
        handler.extract(protected)
