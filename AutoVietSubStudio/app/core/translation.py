from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from .models import SubtitleLine


@dataclass
class TranslationContext:
    mode: str = "Bình thường"
    extra_context: str = ""
    glossary: dict[str, str] | None = None


@dataclass
class TranslationProgress:
    completed: int
    total: int
    percentage: float
    batch_number: int
    total_batches: int
    current_line: int | None = None
    failed_lines: list[int] | None = None
    message: str = ""


class Translator(Protocol):
    def translate(
        self,
        texts: list[str],
        ctx: TranslationContext,
    ) -> list[str]:
        ...


ProgressCallback = Callable[[TranslationProgress], None]


MODE_PROMPTS = {
    "Bình thường": (
        "dịch tự nhiên, trung thành ngữ cảnh, "
        "không thêm giải thích"
    ),
    "Hài hước": (
        "dịch tự nhiên, hài hước vừa phải, "
        "giữ đúng ý nghĩa và bối cảnh"
    ),
    "Ngôn tình": (
        "dịch mềm mại, giàu cảm xúc, "
        "phù hợp hội thoại ngôn tình"
    ),
    "Tu tiên / huyền huyễn": (
        "dùng thuật ngữ tu tiên/huyền huyễn tự nhiên, "
        "giữ nhất quán tên riêng và cảnh giới"
    ),
    "Trung thành nguyên tác": (
        "ưu tiên sát nghĩa, không diễn giải quá mức"
    ),
}


def build_prompt(
    texts: list[str],
    ctx: TranslationContext,
) -> str:
    glossary_text = ""

    if ctx.glossary:
        glossary_text = (
            "\nGlossary:\n"
            + "\n".join(
                f"- {key} => {value}"
                for key, value in ctx.glossary.items()
            )
        )

    style = MODE_PROMPTS.get(
        ctx.mode,
        MODE_PROMPTS["Bình thường"],
    )

    numbered = "\n".join(
        f"{index + 1}. {text}"
        for index, text in enumerate(texts)
    )

    return (
        "Bạn là biên dịch viên subtitle chuyên nghiệp. "
        f"{style}.\n"
        "Giữ nguyên thứ tự số dòng.\n"
        "Chỉ trả lại các câu dịch tương ứng theo đúng số dòng.\n"
        "Không giải thích.\n"
        "Mỗi dòng chỉ là phần thoại.\n"
        "Không tự tạo timestamp.\n"
        f"Ngữ cảnh thêm: {ctx.extra_context or 'không có'}."
        f"{glossary_text}\n\n"
        f"{numbered}"
    )


def _is_valid_translation(text: str | None) -> bool:
    return bool(text and text.strip())


class TranslationEngine:
    def __init__(
        self,
        provider: Translator,
        progress_callback: ProgressCallback | None = None,
    ):
        self.provider = provider
        self.progress_callback = progress_callback

    def _report(
        self,
        *,
        completed: int,
        total: int,
        batch_number: int,
        total_batches: int,
        current_line: int | None = None,
        failed_lines: list[int] | None = None,
        message: str = "",
    ) -> None:
        percentage = 0.0

        if total > 0:
            percentage = (completed / total) * 100.0

        progress = TranslationProgress(
            completed=completed,
            total=total,
            percentage=percentage,
            batch_number=batch_number,
            total_batches=total_batches,
            current_line=current_line,
            failed_lines=list(failed_lines or []),
            message=message,
        )

        if self.progress_callback:
            self.progress_callback(progress)

    def _translate_one(
        self,
        line: SubtitleLine,
        ctx: TranslationContext,
        max_retries: int,
        *,
        completed: int,
        total: int,
        batch_number: int,
        total_batches: int,
        failed_lines: list[int],
    ) -> bool:
        for attempt in range(1, max_retries + 2):
            self._report(
                completed=completed,
                total=total,
                batch_number=batch_number,
                total_batches=total_batches,
                current_line=line.index,
                failed_lines=failed_lines,
                message=(
                    f"Retry dòng #{line.index} "
                    f"(lần {attempt}/{max_retries + 1})"
                ),
            )

            try:
                result = self.provider.translate(
                    [line.original],
                    ctx,
                )

                if len(result) != 1:
                    continue

                translated = result[0]

                if not _is_valid_translation(translated):
                    continue

                line.translated = translated.strip()
                line.status = "translated"

                self._report(
                    completed=completed + 1,
                    total=total,
                    batch_number=batch_number,
                    total_batches=total_batches,
                    current_line=line.index,
                    failed_lines=failed_lines,
                    message=f"Dòng #{line.index}: OK",
                )

                return True

            except Exception:
                continue

        line.status = "translation_failed"

        if line.index not in failed_lines:
            failed_lines.append(line.index)

        self._report(
            completed=completed,
            total=total,
            batch_number=batch_number,
            total_batches=total_batches,
            current_line=line.index,
            failed_lines=failed_lines,
            message=f"Dòng #{line.index}: FAILED",
        )

        return False

    def translate_lines(
        self,
        lines: list[SubtitleLine],
        ctx: TranslationContext,
        batch_size: int = 20,
        max_retries: int = 2,
    ) -> list[int]:
        if batch_size <= 0:
            raise ValueError("batch_size phải lớn hơn 0.")

        if max_retries < 0:
            raise ValueError("max_retries không được âm.")

        total = len(lines)

        if total == 0:
            self._report(
                completed=0,
                total=0,
                batch_number=0,
                total_batches=0,
                message="Không có dòng để dịch.",
            )
            return []

        total_batches = (total + batch_size - 1) // batch_size
        failures: list[int] = []
        completed = 0

        self._report(
            completed=0,
            total=total,
            batch_number=0,
            total_batches=total_batches,
            message=f"Bắt đầu dịch {total} dòng.",
        )

        for batch_index, start in enumerate(
            range(0, total, batch_size),
            start=1,
        ):
            batch = lines[start:start + batch_size]

            batch_line_numbers = [
                line.index
                for line in batch
            ]

            self._report(
                completed=completed,
                total=total,
                batch_number=batch_index,
                total_batches=total_batches,
                failed_lines=failures,
                message=(
                    f"Batch {batch_index}/{total_batches} "
                    f"- dòng #{batch_line_numbers[0]}"
                    f" đến #{batch_line_numbers[-1]}"
                ),
            )

            try:
                translated = self.provider.translate(
                    [line.original for line in batch],
                    ctx,
                )

                if len(translated) != len(batch):
                    raise ValueError(
                        "Provider trả về số lượng bản dịch "
                        "không khớp."
                    )

                for line, text in zip(batch, translated):
                    if _is_valid_translation(text):
                        line.translated = text.strip()
                        line.status = "translated"
                        completed += 1

                        self._report(
                            completed=completed,
                            total=total,
                            batch_number=batch_index,
                            total_batches=total_batches,
                            current_line=line.index,
                            failed_lines=failures,
                            message=f"Dòng #{line.index}: OK",
                        )
                    else:
                        self._translate_one(
                            line,
                            ctx,
                            max_retries,
                            completed=completed,
                            total=total,
                            batch_number=batch_index,
                            total_batches=total_batches,
                            failed_lines=failures,
                        )

                        if line.status == "translated":
                            completed += 1

            except Exception:
                self._report(
                    completed=completed,
                    total=total,
                    batch_number=batch_index,
                    total_batches=total_batches,
                    failed_lines=failures,
                    message=(
                        f"Batch {batch_index}/{total_batches} lỗi. "
                        "Chuyển sang retry từng dòng."
                    ),
                )

                for line in batch:
                    success = self._translate_one(
                        line,
                        ctx,
                        max_retries,
                        completed=completed,
                        total=total,
                        batch_number=batch_index,
                        total_batches=total_batches,
                        failed_lines=failures,
                    )

                    if success:
                        completed += 1

        self._report(
            completed=completed,
            total=total,
            batch_number=total_batches,
            total_batches=total_batches,
            failed_lines=failures,
            message=(
                f"Hoàn tất: {completed}/{total} dòng. "
                f"Lỗi: {failures if failures else 'không có'}"
            ),
        )

        return failures
