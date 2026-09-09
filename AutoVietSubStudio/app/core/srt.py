from __future__ import annotations

import re

from .models import SubtitleLine


TIME_RE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2}),(\d{3})\s+-->\s+"
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})$"
)


def to_ms(hours: str, minutes: str, seconds: str, milliseconds: str) -> int:
    return (
        (
            (int(hours) * 60 + int(minutes)) * 60
            + int(seconds)
        )
        * 1000
        + int(milliseconds)
    )


def from_ms(milliseconds: int) -> str:
    milliseconds = max(0, int(milliseconds))

    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)

    return (
        f"{hours:02}:{minutes:02}:{seconds:02},"
        f"{milliseconds:03}"
    )


def parse_timestamp(value: str) -> int | None:
    match = TIME_RE.match(value.strip())

    if not match:
        return None

    groups = match.groups()

    try:
        start = to_ms(*groups[:4])
        end = to_ms(*groups[4:])
    except ValueError:
        return None

    if end < start:
        return None

    return start, end


def parse_srt(text: str) -> list[SubtitleLine]:
    normalized = (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .strip()
    )

    if not normalized:
        return []

    blocks = re.split(r"\n\s*\n", normalized)
    result: list[SubtitleLine] = []

    for block in blocks:
        lines = block.split("\n")

        if len(lines) < 3:
            continue

        try:
            index = int(lines[0].strip())
        except ValueError:
            continue

        timestamp = parse_timestamp(lines[1])

        if timestamp is None:
            continue

        start_ms, end_ms = timestamp

        original = "\n".join(lines[2:]).strip()

        result.append(
            SubtitleLine(
                index=index,
                start_ms=start_ms,
                end_ms=end_ms,
                original=original,
            )
        )

    return result


def write_srt(
    lines: list[SubtitleLine],
    use_translated: bool = True,
) -> str:
    output: list[str] = []

    for line in lines:
        text = (
            line.translated
            if use_translated
            else line.original
        )

        if text is None:
            text = ""

        output.append(str(line.index))
        output.append(
            f"{from_ms(line.start_ms)} --> "
            f"{from_ms(line.end_ms)}"
        )
        output.append(text)
        output.append("")

    return "\n".join(output)


def validate_alignment(
    original: list[SubtitleLine],
    translated: list[SubtitleLine],
) -> tuple[bool, list[int]]:
    bad: list[int] = []

    if len(original) != len(translated):
        max_length = max(len(original), len(translated))

        for position in range(1, max_length + 1):
            if position > len(original) or position > len(translated):
                bad.append(position)

        return False, bad

    for position, (source, target) in enumerate(
        zip(original, translated),
        start=1,
    ):
        same_index = source.index == target.index
        same_start = source.start_ms == target.start_ms
        same_end = source.end_ms == target.end_ms
        has_translation = bool(target.translated.strip())

        if not (
            same_index
            and same_start
            and same_end
            and has_translation
        ):
            bad.append(position)

    return not bad, bad


def validate_srt_lines(
    lines: list[SubtitleLine],
) -> tuple[bool, list[int]]:
    bad: list[int] = []

    previous_index: int | None = None
    previous_end: int | None = None

    for position, line in enumerate(lines, start=1):
        if line.index <= 0:
            bad.append(position)
            continue

        if line.end_ms <= line.start_ms:
            bad.append(position)
            continue

        if previous_index is not None and line.index <= previous_index:
            bad.append(position)
            continue

        if previous_end is not None and line.start_ms < previous_end:
            bad.append(position)

        previous_index = line.index
        previous_end = line.end_ms

    return not bad, bad
