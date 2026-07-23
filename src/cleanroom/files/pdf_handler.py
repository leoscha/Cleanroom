import hashlib
import os
import tempfile
import unicodedata
from contextlib import suppress
from pathlib import Path

import pymupdf as fitz

from cleanroom.config.settings import Settings
from cleanroom.files.lifecycle import collision_safe
from cleanroom.models.finding import Finding
from cleanroom.models.pdf import (
    BBox,
    PdfCharRef,
    PdfExtractedDocument,
    PdfInspection,
    PdfRedactionMapping,
    PdfSanitizedDocument,
    PdfTextSpan,
)
from cleanroom.models.policy import SanitizationPolicy
from cleanroom.sanitizers.placeholders import PlaceholderFactory
from cleanroom.sanitizers.text_sanitizer import sanitize_text


class PdfError(ValueError):
    pass


class PdfMalformedError(PdfError):
    pass


class PdfEncryptedError(PdfError):
    pass


class PdfUnsupportedError(PdfError):
    def __init__(self, codes: list[str]) -> None:
        self.codes = codes
        super().__init__(f"unsupported PDF ({', '.join(codes)})")


class PdfMappingError(PdfError):
    pass


class PdfVerificationError(PdfError):
    pass


class PdfDocumentHandler:
    supported_extensions = {".pdf"}

    def __init__(self, policy: SanitizationPolicy, settings: Settings) -> None:
        self.policy, self.settings = policy, settings

    def inspect(self, path: Path) -> PdfInspection:
        try:
            with fitz.open(path) as document:  # type: ignore[no-untyped-call]
                return self._inspect_open(document)
        except (fitz.FileDataError, RuntimeError, ValueError) as exc:
            raise PdfMalformedError("PDF cannot be opened safely") from exc

    def _inspect_open(self, document: fitz.Document) -> PdfInspection:
        encrypted = bool(document.needs_pass or document.is_encrypted)
        if encrypted:
            return PdfInspection(page_count=document.page_count,
                extracted_character_count=0, encrypted=True, supported=False,
                rejection_codes=["ENCRYPTED_PDF"])
        annotation_count = form_count = image_count = pages_without_text = 0
        character_count = 0
        external_actions = False
        for page_index in range(document.page_count):
            page = document[page_index]
            text = page.get_text("text")  # type: ignore[no-untyped-call]
            meaningful = sum(not char.isspace() for char in text)
            character_count += meaningful
            pages_without_text += meaningful < self.settings.pdf_min_text_chars_per_page
            image_count += len(page.get_images(full=True))  # type: ignore[no-untyped-call]
            annotations = page.annots()  # type: ignore[no-untyped-call]
            annotation_count += len(list(annotations)) if annotations else 0
            widgets = page.widgets()  # type: ignore[no-untyped-call]
            form_count += len(list(widgets)) if widgets else 0
            for link in page.get_links():
                if link.get("kind") in {fitz.LINK_URI, fitz.LINK_LAUNCH, fitz.LINK_GOTOR}:
                    external_actions = True
        embedded = document.embfile_count()
        javascript = self._has_active_keys(document)
        optional_content = bool(document.get_ocgs())  # type: ignore[no-untyped-call]
        metadata = document.metadata or {}
        metadata_present = any(metadata.get(key) for key in (
            "title", "author", "subject", "keywords", "creator", "producer",
            "creationDate", "modDate")) or bool(
                document.get_xml_metadata()  # type: ignore[no-untyped-call]
            )
        page_count = document.page_count
        scanned = page_count == 0 or character_count < (
            self.settings.pdf_min_text_chars_per_page * max(page_count, 1))
        if image_count and pages_without_text >= max(1, (page_count + 1) // 2):
            scanned = True
        codes: list[str] = []
        if scanned:
            codes.append("LIKELY_SCANNED_PDF")
        if embedded and self.settings.pdf_reject_embedded_files:
            codes.append("EMBEDDED_FILES")
        if form_count and self.settings.pdf_reject_forms:
            codes.append("PDF_FORMS")
        if javascript and self.settings.pdf_reject_javascript:
            codes.append("PDF_JAVASCRIPT")
        if external_actions:
            codes.append("EXTERNAL_ACTIONS")
        if optional_content:
            codes.append("OPTIONAL_CONTENT")
        if annotation_count and not self.settings.pdf_remove_annotations:
            codes.append("PDF_ANNOTATIONS")
        return PdfInspection(page_count=page_count,
            extracted_character_count=character_count, encrypted=False,
            annotations_found=annotation_count, embedded_files_found=embedded,
            forms_found=bool(form_count), javascript_found=javascript,
            external_actions_found=external_actions, optional_content_found=optional_content,
            metadata_present=metadata_present, image_count=image_count,
            pages_without_text=pages_without_text, appears_scanned=scanned,
            supported=not codes, rejection_codes=codes)

    @staticmethod
    def _has_active_keys(document: fitz.Document) -> bool:
        targets = ("/JavaScript", "/JS", "/OpenAction", "/AA", "/Launch")
        for xref in range(1, document.xref_length()):  # type: ignore[no-untyped-call]
            try:
                value = document.xref_object(  # type: ignore[no-untyped-call]
                    xref, compressed=False
                )
            except RuntimeError:
                continue
            if any(target in value for target in targets):
                return True
        return False

    def extract(self, path: Path) -> PdfExtractedDocument:
        try:
            with fitz.open(path) as document:  # type: ignore[no-untyped-call]
                inspection = self._inspect_open(document)
                if inspection.encrypted:
                    raise PdfEncryptedError("encrypted PDFs are not supported")
                if not inspection.supported:
                    raise PdfUnsupportedError(inspection.rejection_codes)
                return self._extract_open(document, path, inspection)
        except PdfError:
            raise
        except (fitz.FileDataError, RuntimeError, ValueError) as exc:
            raise PdfMalformedError("PDF extraction failed safely") from exc

    def extract_output(self, path: Path) -> PdfExtractedDocument:
        try:
            with fitz.open(path) as document:  # type: ignore[no-untyped-call]
                inspection = self._inspect_open(document)
                disallowed = [code for code in inspection.rejection_codes
                              if code != "LIKELY_SCANNED_PDF"]
                if inspection.encrypted or disallowed:
                    raise PdfVerificationError("sanitized PDF contains unsupported structure")
                return self._extract_open(document, path, inspection)
        except PdfError:
            raise
        except (fitz.FileDataError, RuntimeError, ValueError) as exc:
            raise PdfVerificationError("sanitized PDF cannot be reopened") from exc

    def _extract_open(self, document: fitz.Document, path: Path,
                      inspection: PdfInspection) -> PdfExtractedDocument:
        output: list[str] = []
        char_map: list[PdfCharRef | None] = []
        source_spans: dict[tuple[int, int, int, int], tuple[str, BBox]] = {}
        page_ranges: list[tuple[int, int]] = []
        for page_index in range(document.page_count):
            page = document[page_index]
            page_start = len(output)
            raw = page.get_text("rawdict", sort=True)  # type: ignore[no-untyped-call]
            first_line = True
            for block_index, block in enumerate(raw.get("blocks", [])):
                if block.get("type") != 0:
                    continue
                for line_index, line in enumerate(block.get("lines", [])):
                    line_units: list[tuple[str, PdfCharRef]] = []
                    for span_index, span in enumerate(line.get("spans", [])):
                        key = (page_index + 1, block_index, line_index, span_index)
                        source_spans[key] = ("".join(
                            str(char.get("c", "")) for char in span.get("chars", [])),
                            self._bbox(span.get("bbox", (0, 0, 0, 0))))
                        for char_index, char in enumerate(span.get("chars", [])):
                            bbox = self._bbox(char.get("bbox", (0, 0, 0, 0)))
                            ref = PdfCharRef(page_index + 1, block_index, line_index,
                                             span_index, char_index, bbox)
                            normalized = unicodedata.normalize("NFKC", str(char.get("c", "")))
                            for normalized_char in normalized.replace("\u00a0", " "):
                                line_units.append((normalized_char, ref))
                    if not line_units:
                        continue
                    first_char = next((char for char, _ in line_units if not char.isspace()), "")
                    dehyphenate = bool(output and output[-1] == "-" and first_char.isalnum())
                    if dehyphenate:
                        output.pop()
                        char_map.pop()
                    elif not first_line and output and not output[-1].isspace():
                        self._append_normalized(output, char_map, " ", None)
                    for char, ref in line_units:
                        self._append_normalized(output, char_map, char, ref)
                    first_line = False
            while output and output[-1] == " ":
                output.pop()
                char_map.pop()
            page_ranges.append((page_start, len(output)))
            if page_index + 1 < document.page_count:
                output.extend(["\n", "\f", "\n"])
                char_map.extend([None, None, None])
        text = "".join(output)
        positions: dict[tuple[int, int, int, int], list[int]] = {}
        for position, mapped_ref in enumerate(char_map):
            if mapped_ref is not None:
                key = (mapped_ref.page_number, mapped_ref.block_index,
                       mapped_ref.line_index, mapped_ref.span_index)
                positions.setdefault(key, []).append(position)
        spans = tuple(PdfTextSpan(page_number=key[0], text=source_spans[key][0],
            bbox=source_spans[key][1], block_index=key[1], line_index=key[2], span_index=key[3],
            global_start=min(values), global_end=max(values) + 1)
            for key, values in sorted(positions.items()))
        page_text = tuple(text[start:end] for start, end in page_ranges)
        return PdfExtractedDocument(text=text, source_path=path, document_type="pdf",
            file_hash=self._hash(path), page_count=document.page_count,
            extracted_character_count=len(text), page_text=page_text, spans=spans,
            char_map=tuple(char_map), inspection=inspection,
            warnings=tuple(inspection.rejection_codes), extraction_confidence=1.0)

    @staticmethod
    def _append_normalized(output: list[str], mapping: list[PdfCharRef | None],
                           char: str, ref: PdfCharRef | None) -> None:
        if char.isspace():
            if output and output[-1] not in {" ", "\n", "\f"}:
                output.append(" ")
                mapping.append(ref)
            return
        output.append(char)
        mapping.append(ref)

    @staticmethod
    def _bbox(value: object) -> BBox:
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            return (0.0, 0.0, 0.0, 0.0)
        return (float(value[0]), float(value[1]), float(value[2]), float(value[3]))

    def sanitize(self, document: PdfExtractedDocument,
                 findings: list[Finding]) -> PdfSanitizedDocument:
        factory = PlaceholderFactory(self.policy)
        mappings: list[PdfRedactionMapping] = []
        warnings: list[str] = []
        for finding in sorted(findings, key=lambda item: item.start):
            placeholder = factory.for_finding(finding)
            if placeholder is None:
                continue
            rectangles, confidence = self._map_finding(document, finding)
            if confidence < self.settings.pdf_mapping_min_confidence or not rectangles:
                raise PdfMappingError("PDF finding mapping confidence is insufficient")
            mappings.append(PdfRedactionMapping(finding, placeholder, rectangles, confidence))
        sanitized = sanitize_text(document.text, findings, self.policy)
        return PdfSanitizedDocument(text=sanitized.text, source_path=document.source_path,
            document_type="pdf", extracted=document, mappings=tuple(mappings),
            mapping_warnings=tuple(warnings),
            redaction_rectangle_count=sum(len(item.rectangles) for item in mappings))

    def _map_finding(self, document: PdfExtractedDocument,
                     finding: Finding) -> tuple[tuple[tuple[int, BBox], ...], float]:
        if not finding.matches(document.text) or finding.end > len(document.char_map):
            return (), 0.0
        relevant = document.char_map[finding.start:finding.end]
        required = sum(not char.isspace() for char in finding.text)
        mapped_positions = sum(ref is not None for char, ref in zip(
            finding.text, relevant, strict=True)
                               if not char.isspace())
        confidence = mapped_positions / required if required else 1.0
        groups: dict[tuple[int, int, int, int], list[BBox]] = {}
        for ref in relevant:
            if ref is None:
                continue
            key = (ref.page_number, ref.block_index, ref.line_index, ref.span_index)
            groups.setdefault(key, []).append(ref.bbox)
        rectangles = [(key[0], self._union(boxes)) for key, boxes in sorted(groups.items())]
        return tuple(self._merge_adjacent(rectangles)), confidence

    @staticmethod
    def _union(boxes: list[BBox]) -> BBox:
        return (min(box[0] for box in boxes), min(box[1] for box in boxes),
                max(box[2] for box in boxes), max(box[3] for box in boxes))

    @staticmethod
    def _merge_adjacent(rectangles: list[tuple[int, BBox]]) -> list[tuple[int, BBox]]:
        merged: list[tuple[int, BBox]] = []
        for page, box in rectangles:
            if merged:
                prior_page, prior = merged[-1]
                same_line = prior_page == page and abs(prior[1] - box[1]) < 1.5 and abs(prior[3] - box[3]) < 1.5
                if same_line and box[0] - prior[2] <= 2:
                    merged[-1] = (page, (prior[0], min(prior[1], box[1]),
                                             max(prior[2], box[2]), max(prior[3], box[3])))
                    continue
            merged.append((page, box))
        return merged

    def write(self, document: PdfSanitizedDocument, destination: Path) -> Path:
        if document.extracted is None:
            raise PdfError("missing extracted PDF context")
        destination.parent.mkdir(parents=True, exist_ok=True)
        final = collision_safe(destination.parent, destination.name)
        descriptor, temporary = tempfile.mkstemp(prefix=".cleanroom-pdf-", suffix=".pdf",
                                                  dir=destination.parent)
        os.close(descriptor)
        fallbacks = 0
        try:
            with fitz.open(document.source_path) as pdf:  # type: ignore[no-untyped-call]
                if pdf.needs_pass or pdf.is_encrypted:
                    raise PdfEncryptedError("source PDF became encrypted")
                if self.settings.pdf_remove_annotations:
                    for page_index in range(pdf.page_count):
                        page = pdf[page_index]
                        annotations = list(page.annots() or [])
                        for annotation in annotations:
                            page.delete_annot(annotation)
                for mapping in document.mappings:
                    label_written = False
                    for page_number, bbox in mapping.rectangles:
                        page = pdf[page_number - 1]
                        rect = fitz.Rect(bbox)  # type: ignore[no-untyped-call]
                        mode = self.settings.pdf_replacement_mode
                        text: str | None = None
                        fill: tuple[float, float, float] | bool | None = (1, 1, 1)
                        if mode == "black_box":
                            fill = (0, 0, 0)
                        elif mode == "blank":
                            fill = False
                        elif not label_written and self._label_fits(mapping.placeholder, rect):
                            text, label_written = mapping.placeholder, True
                        elif mode == "label":
                            fill = (0, 0, 0)
                            fallbacks += 1
                        page.add_redact_annot(rect, text=text, fontname="helv", fontsize=8,
                                              fill=fill, text_color=(0, 0, 0), cross_out=False)
                for page_index in range(pdf.page_count):
                    page = pdf[page_index]
                    page.apply_redactions(images=0, graphics=0, text=0)
                pdf.scrub(attached_files=True, embedded_files=True, javascript=True,
                          metadata=self.settings.pdf_remove_metadata, redactions=True,
                          remove_links=True, reset_fields=True, xml_metadata=True)
                if self.settings.pdf_remove_metadata:
                    pdf.set_metadata({})
                    with suppress(ValueError, RuntimeError):
                        pdf.del_xml_metadata()
                pdf.save(temporary, garbage=4, clean=True, deflate=True,
                         deflate_images=True, deflate_fonts=True, incremental=False,
                         encryption=1, preserve_metadata=False,
                         use_objstms=1)
            os.replace(temporary, final)
        except BaseException:
            with suppress(FileNotFoundError):
                os.unlink(temporary)
            raise
        document.write_telemetry.update({"label_fallback_count": fallbacks,
                                         "metadata_removed": self.settings.pdf_remove_metadata})
        return final

    @staticmethod
    def _label_fits(label: str, rect: fitz.Rect) -> bool:
        width = float(fitz.get_text_length(label, fontname="helv", fontsize=8))
        return bool(rect.height >= 8 and width <= rect.width)

    def verify_output(self, path: Path, expected_page_count: int | None = None) -> dict[str, object]:
        inspection = self.inspect(path)
        passed = (not inspection.encrypted and inspection.embedded_files_found == 0
                  and not inspection.javascript_found and not inspection.forms_found
                  and inspection.annotations_found == 0 and not inspection.metadata_present
                  and not inspection.external_actions_found and not inspection.optional_content_found
                  and (expected_page_count is None or inspection.page_count == expected_page_count))
        return {"passed": passed, "page_count_preserved": expected_page_count is None
                or inspection.page_count == expected_page_count,
                "metadata_sanitized": not inspection.metadata_present,
                "embedded_files_remaining": inspection.embedded_files_found,
                "javascript_remaining": inspection.javascript_found,
                "forms_remaining": inspection.forms_found,
                "annotations_remaining": inspection.annotations_found}

    def verify_original_absence(self, path: Path,
                                findings: list[Finding]) -> dict[str, object]:
        """Check normal extraction, text dictionaries, and metadata in the saved PDF."""
        normal_parts: list[str] = []
        dictionary_parts: list[str] = []
        metadata_parts: list[str] = []
        try:
            with fitz.open(path) as document:  # type: ignore[no-untyped-call]
                metadata_parts.extend(str(value) for value in (document.metadata or {}).values())
                metadata_parts.append(document.get_xml_metadata())
                for page_index in range(document.page_count):
                    page = document[page_index]
                    normal_parts.append(page.get_text("text"))
                    raw = page.get_text("rawdict")
                    for block in raw.get("blocks", []):
                        for line in block.get("lines", []):
                            dictionary_parts.append("".join(
                                str(char.get("c", ""))
                                for span in line.get("spans", [])
                                for char in span.get("chars", [])
                            ))
            normal = "\n".join(normal_parts)
            dictionary_text = "\n".join(dictionary_parts)
            metadata_text = "\n".join(metadata_parts)
            normal_remaining = sum(item.text in normal for item in findings)
            dictionary_remaining = sum(item.text in dictionary_text for item in findings)
            metadata_remaining = sum(item.text in metadata_text for item in findings)
            passed = not (normal_remaining or dictionary_remaining or metadata_remaining)
            return {"passed": passed,
                    "normal_extraction_values_remaining": normal_remaining,
                    "text_dictionary_values_remaining": dictionary_remaining,
                    "metadata_values_remaining": metadata_remaining,
                    "redactions_flattened": self.inspect(path).annotations_found == 0}
        except (fitz.FileDataError, RuntimeError, ValueError) as exc:
            raise PdfVerificationError("PDF recovery-resistance checks failed") from exc

    @staticmethod
    def _hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while block := handle.read(1024 * 1024):
                digest.update(block)
        return digest.hexdigest()


def create_synthetic_pdf(path: Path) -> None:
    document = fitz.open()  # type: ignore[no-untyped-call]
    try:
        page = document.new_page(width=612, height=792)
        page.insert_textbox(fitz.Rect(72, 72, 540, 240),  # type: ignore[no-untyped-call]
            "Synthetic Test Fields\n\nEmail: jane@example.test\n"
            "Phone: 312-555-0199\nSupport password = TestingOnly123!",
            fontname="helv", fontsize=12, lineheight=1.4)
        document.set_metadata({"title": "Synthetic private demo",
                               "author": "Cleanroom synthetic fixture"})
        document.save(path, garbage=4, clean=True, deflate=True)  # type: ignore[no-untyped-call]
    finally:
        document.close()  # type: ignore[no-untyped-call]
