"""PDF extraction. INGESTION_SPEC.md §4.2 (P1-P7).

P4 (heading detection from font-size runs) is deliberately not implemented: pypdf's
`extract_text()` does not expose per-run font metadata, and the spec explicitly allows leaving
`sections` empty rather than guessing from heuristics like ALL-CAPS. PDFs therefore chunk on
paragraph/sentence/token boundaries only; DOCX (python-docx exposes paragraph styles directly)
gets the richer section_path.
"""

from typing import BinaryIO

import pypdf
from pypdf._encryption import PasswordType

from app.config import settings
from app.errors import IngestionError
from app.ingestion.extractors.base import ExtractedDocument, PageSpan
from app.schemas.enums import IngestionFailureCode

_PAGE_SEPARATOR = "\n\n"


def extract_pdf(stream: BinaryIO) -> ExtractedDocument:
    try:
        reader = pypdf.PdfReader(stream)
    except Exception as exc:
        raise IngestionError(
            IngestionFailureCode.EXTRACTION_PARSER_ERROR,
            f"Could not open PDF: {exc}",
            retryable=False,
        ) from exc

    # P1: encrypted and no empty-password decrypt succeeds -> terminal.
    if reader.is_encrypted:
        try:
            result = reader.decrypt("")
        except Exception:
            result = PasswordType.NOT_DECRYPTED
        if result == PasswordType.NOT_DECRYPTED:
            raise IngestionError(
                IngestionFailureCode.EXTRACTION_ENCRYPTED_DOCUMENT,
                "Document is password-protected.",
                retryable=False,
            )

    try:
        page_count = len(reader.pages)
    except Exception as exc:
        raise IngestionError(
            IngestionFailureCode.EXTRACTION_PARSER_ERROR,
            f"Could not read page tree: {exc}",
            retryable=False,
        ) from exc

    # P2
    if page_count > settings.max_document_pages:
        raise IngestionError(
            IngestionFailureCode.EXTRACTION_PARSER_ERROR,
            f"Document exceeds the {settings.max_document_pages}-page limit.",
            retryable=False,
        )

    # P3/P7: extract text page by page; tolerate isolated failures.
    text_parts: list[str] = []
    page_spans: list[PageSpan] = []
    offset = 0
    failed_pages = 0
    total_extracted_chars = 0
    for page_no, page in enumerate(reader.pages, start=1):
        try:
            page_text = page.extract_text() or ""
        except Exception:
            failed_pages += 1
            continue

        if text_parts:
            text_parts.append(_PAGE_SEPARATOR)
            offset += len(_PAGE_SEPARATOR)

        start = offset
        text_parts.append(page_text)
        offset += len(page_text)
        total_extracted_chars += len(page_text)
        page_spans.append(PageSpan(page_no=page_no, char_start=start, char_end=offset))

    if page_count > 0 and failed_pages / page_count > settings.pdf_max_failed_page_ratio:
        raise IngestionError(
            IngestionFailureCode.EXTRACTION_PARSER_ERROR,
            f"{failed_pages} of {page_count} pages failed to extract.",
            retryable=False,
        )

    # P6 checked before P5: ING-013 motivates P5 as the *scanned*-PDF detector, catching "a
    # handful of stray characters rather than none" — i.e. 0 < chars < EXTRACTION_MIN_CHARS.
    # A genuinely blank document (0 chars) is EXTRACTION_EMPTY_DOCUMENT regardless of page
    # count; the fixture corpus (tests/fixtures/verify.py) encodes this same reading for a
    # one-page, zero-content PDF. Taking P5's literal "< 200" at face value (without excluding
    # zero) would make P6 fire only for a 0-page PDF and misclassify every blank document as a
    # scan, contradicting both ING-013's own rationale and that fixture.
    if total_extracted_chars == 0:
        raise IngestionError(
            IngestionFailureCode.EXTRACTION_EMPTY_DOCUMENT,
            "Document contains no extractable text.",
            retryable=False,
        )

    # P5: the scanned-PDF detector — characters, not pages, because a scan usually yields a
    # handful of stray characters rather than exactly zero.
    if total_extracted_chars < settings.extraction_min_chars and page_count >= 1:
        raise IngestionError(
            IngestionFailureCode.EXTRACTION_NO_TEXT_LAYER,
            f"No extractable text layer found ({page_count} pages scanned, "
            f"{total_extracted_chars} characters recovered). OCR is not supported.",
            retryable=False,
        )
    return ExtractedDocument(
        text="".join(text_parts),
        page_spans=tuple(page_spans),
        sections=(),
        page_count=page_count,
        extractor=f"pypdf-{pypdf.__version__}",
    )
