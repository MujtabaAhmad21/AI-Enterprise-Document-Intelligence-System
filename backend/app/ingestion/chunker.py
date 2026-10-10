"""Chunking. INGESTION_SPEC.md §6 (K1-K8).

Uses LlamaIndex's sentence-splitting utility (C-1: "configured, not extended") for the
sentence unit and tiktoken for the embedding model's tokenizer (ING-020); the section- and
paragraph-aware greedy accumulation (K2-K7) is this module's own, since neither library
implements section-boundary-respecting chunking.

Pure function of (normalized_text, page_spans, sections, config) — same input, same chunks
(ING-024, required for FR-034 idempotency).
"""

import hashlib
import re
from dataclasses import dataclass

import tiktoken
from llama_index.core.node_parser.text.utils import split_by_sentence_tokenizer

from app.config import settings
from app.errors import IngestionError
from app.ingestion.extractors.base import PageSpan, SectionSpan
from app.schemas.enums import IngestionFailureCode

_PARAGRAPH_SPLIT_RE = re.compile(r"\n{2,}")


@dataclass(frozen=True)
class ChunkDraft:
    ordinal: int
    content: str
    content_hash: str
    token_count: int
    char_start: int
    char_end: int
    page_start: int | None
    page_end: int | None
    section_path: str | None


@dataclass(frozen=True)
class _Unit:
    char_start: int
    char_end: int
    token_count: int
    section_path: str | None


def _get_encoding() -> tiktoken.Encoding:
    try:
        return tiktoken.encoding_for_model(settings.embedding_model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def _split_paragraphs(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    pos = 0
    for match in _PARAGRAPH_SPLIT_RE.finditer(text):
        if match.start() > pos:
            spans.append((pos, match.start()))
        pos = match.end()
    if pos < len(text):
        spans.append((pos, len(text)))
    return spans


def _section_at(index: int, sections: tuple[SectionSpan, ...]) -> str | None:
    for section in sections:
        if section.char_start <= index < section.char_end:
            return section.section_path
    return None


def _force_split_oversized(
    text: str, abs_start: int, encoding: tiktoken.Encoding, target_tokens: int
) -> list[tuple[int, int, int]]:
    """K4: split a too-large unit into pieces of <= target_tokens, snapped to word
    boundaries (never inside a word). Returns (char_start, char_end, token_count) triples."""
    pieces: list[tuple[int, int, int]] = []
    char_pos = 0
    while char_pos < len(text):
        remaining = text[char_pos:]
        tokens = encoding.encode(remaining)
        if len(tokens) <= target_tokens:
            pieces.append((abs_start + char_pos, abs_start + len(text), len(tokens)))
            break

        piece_text = encoding.decode(tokens[:target_tokens])
        end_char = char_pos + len(piece_text)
        mid_word = (
            end_char < len(text)
            and not text[end_char - 1].isspace()
            and not text[end_char].isspace()
        )
        if mid_word:
            last_space = remaining.rfind(" ", 0, len(piece_text))
            if last_space > 0:
                end_char = char_pos + last_space

        piece_text = text[char_pos:end_char]
        piece_tokens = len(encoding.encode(piece_text))
        pieces.append((abs_start + char_pos, abs_start + end_char, piece_tokens))
        char_pos = end_char

    return pieces


def _build_units(
    text: str, sections: tuple[SectionSpan, ...], encoding: tiktoken.Encoding
) -> list[_Unit]:
    units: list[_Unit] = []
    sentence_splitter = split_by_sentence_tokenizer()

    for para_start, para_end in _split_paragraphs(text):
        paragraph = text[para_start:para_end]
        if not paragraph.strip():
            continue

        local_pos = 0
        for sentence in sentence_splitter(paragraph):
            sent_start = para_start + local_pos
            sent_end = sent_start + len(sentence)
            local_pos += len(sentence)
            if not sentence.strip():
                continue

            token_count = len(encoding.encode(sentence))
            if token_count > settings.chunk_max_tokens:
                for piece_start, piece_end, piece_tokens in _force_split_oversized(
                    sentence, sent_start, encoding, settings.chunk_target_tokens
                ):
                    units.append(
                        _Unit(
                            char_start=piece_start,
                            char_end=piece_end,
                            token_count=piece_tokens,
                            section_path=_section_at(piece_start, sections),
                        )
                    )
            else:
                units.append(
                    _Unit(
                        char_start=sent_start,
                        char_end=sent_end,
                        token_count=token_count,
                        section_path=_section_at(sent_start, sections),
                    )
                )
    return units


def _compute_overlap(prev_units: list[_Unit], overlap_tokens: int) -> list[_Unit]:
    """K5: trailing units of the just-emitted chunk, snapped outward (whole sentences) to
    at least overlap_tokens."""
    if overlap_tokens <= 0:
        return []
    overlap: list[_Unit] = []
    total = 0
    for unit in reversed(prev_units):
        overlap.insert(0, unit)
        total += unit.token_count
        if total >= overlap_tokens:
            break
    return overlap


def _group_units_into_chunks(units: list[_Unit]) -> list[list[_Unit]]:
    groups: list[list[_Unit]] = []
    current: list[_Unit] = []
    current_tokens = 0
    current_section: str | None = None

    target = settings.chunk_target_tokens
    for unit in units:
        crosses_section = bool(current) and unit.section_path != current_section
        would_exceed = bool(current) and current_tokens + unit.token_count > target

        if current and (would_exceed or crosses_section):
            groups.append(current)
            if crosses_section:
                current = []
            else:
                overlap = _compute_overlap(current, settings.chunk_overlap_tokens)
                overlap_tokens = sum(u.token_count for u in overlap)
                # Hard guard: CHUNK_MAX_TOKENS must never be violated, even though
                # CHUNK_OVERLAP_TOKENS is allowed to slightly overshoot CHUNK_TARGET_TOKENS
                # (ING-022). If the overlap alone would already collide with the very next
                # unit, drop the overlap for this transition rather than break the ceiling.
                # A single unit is always <= CHUNK_TARGET_TOKENS <= CHUNK_MAX_TOKENS (K4), so
                # appending it to an empty `current` can never itself violate the ceiling —
                # this decision is made once per transition, never revisited/looped.
                over_max = overlap_tokens + unit.token_count > settings.chunk_max_tokens
                current = [] if over_max else overlap
            current_tokens = sum(u.token_count for u in current)

        current.append(unit)
        current_tokens += unit.token_count
        current_section = unit.section_path

    if current:
        groups.append(current)

    # K6: a too-small final chunk merges into the previous one, unless that would exceed
    # CHUNK_MAX_TOKENS, in which case it is emitted as-is.
    if len(groups) >= 2:
        last_tokens = sum(u.token_count for u in groups[-1])
        if last_tokens < settings.chunk_min_tokens:
            merged_tokens = sum(u.token_count for u in groups[-2]) + last_tokens
            if merged_tokens <= settings.chunk_max_tokens:
                tail = groups.pop()
                groups[-1] = groups[-1] + tail

    return groups


def _pages_covering(
    char_start: int, char_end: int, page_spans: tuple[PageSpan, ...]
) -> tuple[int | None, int | None]:
    covering = [p for p in page_spans if p.char_start < char_end and p.char_end > char_start]
    if not covering:
        return None, None
    return covering[0].page_no, covering[-1].page_no


def chunk_document(
    normalized_text: str,
    page_spans: tuple[PageSpan, ...],
    sections: tuple[SectionSpan, ...],
) -> list[ChunkDraft]:
    encoding = _get_encoding()
    units = _build_units(normalized_text, sections, encoding)
    groups = _group_units_into_chunks(units)

    drafts: list[ChunkDraft] = []
    for ordinal, group in enumerate(groups):
        char_start = group[0].char_start
        char_end = group[-1].char_end
        content = normalized_text[char_start:char_end]
        token_count = len(encoding.encode(content))
        page_start, page_end = _pages_covering(char_start, char_end, page_spans)
        section_path = _section_at(char_start, sections)

        drafts.append(
            ChunkDraft(
                ordinal=ordinal,
                content=content,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                token_count=token_count,
                char_start=char_start,
                char_end=char_end,
                page_start=page_start,
                page_end=page_end,
                section_path=section_path,
            )
        )

    if not drafts:
        raise IngestionError(
            IngestionFailureCode.CHUNKING_PRODUCED_NO_CHUNKS,
            "Document text was too short to produce any chunks.",
            retryable=False,
        )

    return drafts
