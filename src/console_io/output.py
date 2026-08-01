from __future__ import annotations

import re


_FENCED_CODE = re.compile(
    r"```.*?```",
    flags=re.DOTALL,
)
_LIST_OR_STRUCTURE = re.compile(
    r"^\s*(?:[-+*]|\d+[.)]|#{1,6}\s|>|\|)"
)
_SENTENCE_BOUNDARY = re.compile(
    r"(?<=[.!?。！？])(?:\s+|(?=[가-힣A-Z]))"
)


def split_reply_units(text: str) -> tuple[str, ...]:
    """Split prose into sentences while keeping code/list lines intact."""

    cleaned = text.strip()
    if not cleaned:
        return ("<empty>",)

    units: list[str] = []
    cursor = 0
    for match in _FENCED_CODE.finditer(cleaned):
        _append_plain_units(
            units,
            cleaned[cursor:match.start()],
        )
        code = match.group(0).strip()
        if code:
            units.append(code)
        cursor = match.end()
    _append_plain_units(units, cleaned[cursor:])

    return tuple(units) or (cleaned,)


def _append_plain_units(
    units: list[str],
    value: str,
) -> None:
    for raw_line in value.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _LIST_OR_STRUCTURE.match(line):
            units.append(line)
            continue
        sentences = [
            item.strip()
            for item in _SENTENCE_BOUNDARY.split(line)
            if item.strip()
        ]
        units.extend(sentences or [line])


def format_numbered_reply(
    text: str,
    *,
    speaker: str = "JARVIS",
) -> str:
    units = split_reply_units(text)
    total = len(units)
    width = len(str(total))
    lines: list[str] = []

    for index, unit in enumerate(units, start=1):
        name = speaker if index == 1 else " " * len(speaker)
        counter = f"{index:>{width}}/{total}"
        prefix = f"{name} | {counter} | "
        parts = unit.splitlines() or [unit]
        lines.append(prefix + parts[0])
        continuation = " " * len(prefix)
        lines.extend(
            continuation + part
            for part in parts[1:]
        )

    return "\n".join(lines)


def print_numbered_reply(
    text: str,
    *,
    speaker: str = "JARVIS",
) -> None:
    print(format_numbered_reply(text, speaker=speaker))
