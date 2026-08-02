from __future__ import annotations

from urllib.parse import urlsplit
import re


_PAREN_MARKDOWN_LINK = re.compile(
    r"\(\s*\[([^\]\n]+)\]\((https?://[^\s<>\n]+)\)\s*\)",
    flags=re.IGNORECASE,
)
_MARKDOWN_LINK = re.compile(
    r"\[([^\]\n]+)\]\((https?://[^\s<>\n]+)\)",
    flags=re.IGNORECASE,
)
_PAREN_RAW_URL = re.compile(
    r"\(\s*https?://[^\s<>\n]+\s*\)",
    flags=re.IGNORECASE,
)
_RAW_URL = re.compile(
    r"https?://[^\s<>\n]+",
    flags=re.IGNORECASE,
)
_NUMERIC_CITATION = re.compile(
    r"(?<!\w)\[(?:\d+(?:\s*[,–-]\s*\d+)*)\]"
)
_EMPTY_WRAPPER = re.compile(
    r"\(\s*\)|\[\s*\]"
)
_SPACE_BEFORE_PUNCTUATION = re.compile(
    r"\s+([,.;:!?。！？])"
)
_MULTIPLE_SPACES = re.compile(r"[ \t]{2,}")
_CITATION_ONLY_LABELS = {
    "source",
    "sources",
    "link",
    "reference",
    "references",
    "출처",
    "링크",
    "참고",
    "참고자료",
}


def _clean_url_for_domain(url: str) -> str:
    return url.rstrip(".,;:!?)]}\'\"")


def _looks_like_citation_label(
    label: str,
    url: str,
) -> bool:
    cleaned_label = " ".join(
        label.strip().split()
    )
    normalized = cleaned_label.casefold()

    if not cleaned_label:
        return True
    if normalized in _CITATION_ONLY_LABELS:
        return True
    if re.fullmatch(r"\d+(?:\s*[,–-]\s*\d+)*", normalized):
        return True

    parsed = urlsplit(
        _clean_url_for_domain(url)
    )
    domain = parsed.netloc.casefold()
    if domain.startswith("www."):
        domain = domain[4:]

    label_domain = normalized.removeprefix("www.")
    if domain and (
        label_domain == domain
        or label_domain == domain.split(":", 1)[0]
    ):
        return True

    if re.fullmatch(
        r"(?:[a-z0-9-]+\.)+[a-z]{2,}(?::\d+)?",
        label_domain,
        flags=re.IGNORECASE,
    ):
        return True

    return False


def _replace_parenthesized_link(
    match: re.Match[str],
) -> str:
    label, url = match.groups()
    if _looks_like_citation_label(
        label,
        url,
    ):
        return ""
    return label.strip()


def _replace_markdown_link(
    match: re.Match[str],
) -> str:
    label, url = match.groups()
    if _looks_like_citation_label(
        label,
        url,
    ):
        return ""
    return label.strip()


def _clean_line(line: str) -> str:
    cleaned = _PAREN_MARKDOWN_LINK.sub(
        _replace_parenthesized_link,
        line,
    )
    cleaned = _MARKDOWN_LINK.sub(
        _replace_markdown_link,
        cleaned,
    )
    cleaned = _PAREN_RAW_URL.sub(
        "",
        cleaned,
    )
    cleaned = _RAW_URL.sub(
        "",
        cleaned,
    )
    cleaned = _NUMERIC_CITATION.sub(
        "",
        cleaned,
    )
    cleaned = _EMPTY_WRAPPER.sub(
        "",
        cleaned,
    )
    cleaned = _SPACE_BEFORE_PUNCTUATION.sub(
        r"\1",
        cleaned,
    )
    cleaned = _MULTIPLE_SPACES.sub(
        " ",
        cleaned,
    ).strip()

    if cleaned in {
        "-",
        "*",
        "•",
        "()",
        "[]",
    }:
        return ""
    return cleaned


def sanitize_web_citations(
    text: str,
) -> str:
    """Remove citation URLs while preserving useful answer text."""

    cleaned_lines = [
        cleaned
        for raw_line in text.splitlines()
        if (cleaned := _clean_line(raw_line))
    ]
    return "\n".join(cleaned_lines).strip()


def sanitize_tts_chunk(
    text: str,
) -> str:
    """Keep URLs and citation-only lines out of spoken output."""

    return sanitize_web_citations(text)
