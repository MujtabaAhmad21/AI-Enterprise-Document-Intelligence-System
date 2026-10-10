"""Text normalisation. INGESTION_SPEC.md §5 (N1-N10), RAG-004.

Pure function `normalize(text) -> (normalized_text, offset_map)`. `offset_map[j]` is the index
in the ORIGINAL (pre-normalisation) text that produced `normalized_text[j]` — composed across
every step via generic sequence alignment (difflib), so each step below stays a simple,
independently-readable `str -> str` transform matching its N-number literally, rather than
hand-tracking positions through every substitution.
"""

import bisect
import difflib
import re
import unicodedata

_LIGATURES = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
}
_EXOTIC_SPACES = "    "
# Keep \n and \t; strip other C0/C1 control characters.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_DEHYPHENATE_RE = re.compile(r"(\w+)-\n(\w+)")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_HORIZONTAL_WS_RUN_RE = re.compile(r"[ \t]+")
_TRAILING_HORIZONTAL_WS_RE = re.compile(r"[ \t]+$", re.MULTILINE)


def _n1_nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def _n2_expand_ligatures(text: str) -> str:
    for ligature, expansion in _LIGATURES.items():
        text = text.replace(ligature, expansion)
    return text


def _n3_strip_control_chars(text: str) -> str:
    return _CONTROL_CHARS_RE.sub("", text)


def _n4_normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _n5_dehyphenate(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        word1, word2 = match.group(1), match.group(2)
        hyphenated_form = f"{word1}-{word2}"
        # Guard: don't join if the hyphenated form (no newline) is a genuine compound
        # appearing elsewhere in the document (e.g. "end-to-end" wrapping as "end-\nto-end").
        # match.group(0) always contains a newline, so it can never equal hyphenated_form —
        # any occurrence found is necessarily a distinct, non-wrapped instance.
        if hyphenated_form in text:
            return match.group(0)
        return word1 + word2

    return _DEHYPHENATE_RE.sub(repl, text)


def _n6_replace_exotic_spaces(text: str) -> str:
    for ch in _EXOTIC_SPACES:
        text = text.replace(ch, " ")
    return text


def _n7_collapse_blank_lines(text: str) -> str:
    return _MULTI_NEWLINE_RE.sub("\n\n", text)


def _n8_collapse_horizontal_whitespace(text: str) -> str:
    return _HORIZONTAL_WS_RUN_RE.sub(" ", text)


def _n9_strip_trailing_line_whitespace(text: str) -> str:
    return _TRAILING_HORIZONTAL_WS_RE.sub("", text)


def _n10_strip_document(text: str) -> str:
    return text.strip()


_STEPS = (
    _n1_nfkc,
    _n2_expand_ligatures,
    _n3_strip_control_chars,
    _n4_normalize_line_endings,
    _n5_dehyphenate,
    _n6_replace_exotic_spaces,
    _n7_collapse_blank_lines,
    _n8_collapse_horizontal_whitespace,
    _n9_strip_trailing_line_whitespace,
    _n10_strip_document,
)


def _align(old: str, new: str, old_map: list[int]) -> list[int]:
    """new_map[j] = old_map[i] for the source position i that produced new[j]."""
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    new_map = [0] * len(new)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(j2 - j1):
                new_map[j1 + k] = old_map[i1 + k]
        elif tag == "replace":
            span = old_map[i1:i2]
            if not span:
                span = [old_map[i1 - 1]] if i1 > 0 else [old_map[0]] if old_map else [0]
            for k in range(j2 - j1):
                new_map[j1 + k] = span[min(k, len(span) - 1)]
        elif tag == "insert":
            anchor = old_map[i1 - 1] if i1 > 0 else (old_map[0] if old_map else 0)
            for k in range(j2 - j1):
                new_map[j1 + k] = anchor
        # "delete": those source characters vanish; nothing to assign.
    return new_map


def normalize(text: str) -> tuple[str, list[int]]:
    """Returns (normalized_text, offset_map). ING-018: lossless with respect to meaning — no
    words removed, no case changes, no punctuation stripped."""
    position_map = list(range(len(text)))
    current = text
    for step in _STEPS:
        next_text = step(current)
        if next_text != current:
            position_map = _align(current, next_text, position_map)
            current = next_text
    return current, position_map


def remap_offset(original_index: int, offset_map: list[int]) -> int:
    """The first index into the normalised text whose source position is >= original_index.
    offset_map is weakly non-decreasing by construction, so bisection is valid."""
    return bisect.bisect_left(offset_map, original_index)


def remap_span(char_start: int, char_end: int, offset_map: list[int]) -> tuple[int, int]:
    """Remaps a [char_start, char_end) span in the ORIGINAL (pre-normalisation) text into the
    normalised text's coordinate space."""
    return remap_offset(char_start, offset_map), remap_offset(char_end, offset_map)
