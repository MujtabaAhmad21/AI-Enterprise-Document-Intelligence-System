"""Extraction output contract. INGESTION_SPEC.md §4.1, RAG-003.

Offsets are into `text` as returned here (pre-normalisation) — RAG-004 requires normalisation
to remap them so page/section boundaries stay accurate against the normalised text.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PageSpan:
    page_no: int
    char_start: int
    char_end: int


@dataclass(frozen=True)
class SectionSpan:
    section_path: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class ExtractedDocument:
    text: str
    page_spans: tuple[PageSpan, ...]
    sections: tuple[SectionSpan, ...]
    page_count: int | None
    extractor: str
