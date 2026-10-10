"""DOCX extraction. INGESTION_SPEC.md §4.3 (D1-D5).

SEC-031: XXE is mitigated by python-docx's own XML parser configuration
(`docx.oxml.parser.oxml_parser` is an `lxml.etree.XMLParser(resolve_entities=False)`) — an
external entity reference in `document.xml` is never resolved into the parsed tree, so `&xxe;`
comes through as literal, unresolved text rather than fetching or inlining anything.
"""

from collections.abc import Iterator
from typing import BinaryIO

import docx
from docx.document import Document as DocxDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.errors import IngestionError
from app.ingestion.extractors.base import ExtractedDocument, SectionSpan
from app.schemas.enums import IngestionFailureCode

_HEADING_LEVELS = {f"Heading {i}": i for i in range(1, 7)}


def _iter_block_items(document: DocxDocument) -> Iterator[Paragraph | Table]:
    """D2: walk the document body in order — paragraphs and tables, headers/footers excluded
    by construction (they live in separate XML parts, never touched here)."""
    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def extract_docx(stream: BinaryIO) -> ExtractedDocument:
    try:
        document = docx.Document(stream)
    except Exception as exc:
        raise IngestionError(
            IngestionFailureCode.EXTRACTION_PARSER_ERROR,
            f"Could not open DOCX: {exc}",
            retryable=False,
        ) from exc

    text_parts: list[str] = []
    sections: list[SectionSpan] = []
    heading_stack: list[str] = []
    heading_levels: list[int] = []
    offset = 0
    section_start = 0
    current_path = ""

    def flush_section(end: int) -> None:
        nonlocal section_start
        if current_path and end > section_start:
            sections.append(
                SectionSpan(section_path=current_path, char_start=section_start, char_end=end)
            )
        section_start = end

    for block in _iter_block_items(document):
        if isinstance(block, Paragraph):
            style_name = block.style.name if block.style is not None else None
            level = _HEADING_LEVELS.get(style_name) if style_name else None
            if level is not None:
                # D3: heading stack — pop back to this level, then push.
                flush_section(offset)
                while heading_levels and heading_levels[-1] >= level:
                    heading_levels.pop()
                    heading_stack.pop()
                heading_text = block.text.strip()
                if heading_text:
                    heading_stack.append(heading_text)
                    heading_levels.append(level)
                current_path = " > ".join(heading_stack)

            text_parts.append(block.text)
            offset += len(block.text)
            text_parts.append("\n")
            offset += 1
        else:
            # D2: table cells, row-major, joined by " | ", each row on its own line.
            for row in block.rows:
                row_text = " | ".join(cell.text for cell in row.cells)
                text_parts.append(row_text)
                offset += len(row_text)
                text_parts.append("\n")
                offset += 1

    flush_section(offset)

    full_text = "".join(text_parts)

    # D5
    if len(full_text.strip()) == 0:
        raise IngestionError(
            IngestionFailureCode.EXTRACTION_EMPTY_DOCUMENT,
            "Document contains no extractable text.",
            retryable=False,
        )

    return ExtractedDocument(
        text=full_text,
        page_spans=(),  # D4: DOCX has no page model before rendering.
        sections=tuple(sections),
        page_count=None,
        extractor=f"python-docx-{docx.__version__}",
    )
