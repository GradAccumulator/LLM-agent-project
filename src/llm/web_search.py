from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class WebSource:
    title: str
    url: str
    source_type: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "title": self.title,
            "url": self.url,
            "source_type": self.source_type,
        }


@dataclass(frozen=True, slots=True)
class WebSearchMetadata:
    call_count: int
    queries: tuple[str, ...]
    sources: tuple[WebSource, ...]


def _field(
    value: Any,
    name: str,
    default: Any = None,
) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _items(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, dict)):
        return (value,)
    try:
        return tuple(value)
    except TypeError:
        return (value,)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _append_query(
    queries: list[str],
    seen: set[str],
    value: Any,
) -> None:
    query = _clean_text(value)
    key = query.casefold()
    if query and key not in seen:
        seen.add(key)
        queries.append(query)


def _append_source(
    sources: list[WebSource],
    seen: set[str],
    value: Any,
) -> None:
    nested = _field(value, "url_citation")
    if nested is not None:
        value = nested

    url = _clean_text(_field(value, "url"))
    if not url:
        return

    key = url.casefold()
    if key in seen:
        return

    title = _clean_text(_field(value, "title"))
    source_type = _clean_text(
        _field(value, "type")
    ) or None
    seen.add(key)
    sources.append(
        WebSource(
            title=title or url,
            url=url,
            source_type=source_type,
        )
    )


def extract_web_search_metadata(
    response: Any,
) -> WebSearchMetadata:
    """Extract hosted-search calls, queries, and cited URLs."""

    call_count = 0
    queries: list[str] = []
    query_seen: set[str] = set()
    sources: list[WebSource] = []
    source_seen: set[str] = set()

    for output_item in _items(
        _field(response, "output", ())
    ):
        item_type = _clean_text(
            _field(output_item, "type")
        )

        if item_type == "web_search_call":
            call_count += 1
            action = _field(
                output_item,
                "action",
                {},
            )
            _append_query(
                queries,
                query_seen,
                _field(action, "query"),
            )
            for query in _items(
                _field(action, "queries", ())
            ):
                _append_query(
                    queries,
                    query_seen,
                    query,
                )
            for source in _items(
                _field(action, "sources", ())
            ):
                _append_source(
                    sources,
                    source_seen,
                    source,
                )

        if item_type != "message":
            continue

        for content in _items(
            _field(output_item, "content", ())
        ):
            for annotation in _items(
                _field(
                    content,
                    "annotations",
                    (),
                )
            ):
                annotation_type = _clean_text(
                    _field(annotation, "type")
                )
                if (
                    annotation_type
                    == "url_citation"
                    or _field(
                        annotation,
                        "url_citation",
                    )
                    is not None
                ):
                    _append_source(
                        sources,
                        source_seen,
                        annotation,
                    )

    return WebSearchMetadata(
        call_count=call_count,
        queries=tuple(queries),
        sources=tuple(sources),
    )


def merge_web_search_metadata(
    metadata_items: Iterable[WebSearchMetadata],
) -> WebSearchMetadata:
    call_count = 0
    queries: list[str] = []
    query_seen: set[str] = set()
    sources: list[WebSource] = []
    source_seen: set[str] = set()

    for metadata in metadata_items:
        call_count += metadata.call_count

        for query in metadata.queries:
            key = query.casefold()
            if key not in query_seen:
                query_seen.add(key)
                queries.append(query)

        for source in metadata.sources:
            key = source.url.casefold()
            if key not in source_seen:
                source_seen.add(key)
                sources.append(source)

    return WebSearchMetadata(
        call_count=call_count,
        queries=tuple(queries),
        sources=tuple(sources),
    )
