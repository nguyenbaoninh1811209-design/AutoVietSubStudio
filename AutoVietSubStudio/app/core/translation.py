from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from .models import SubtitleLine


@dataclass
class TranslationContext:
    source_language: str = "auto"
    target_language: str = "vi"
    mode: str = "Bình thường"
    extra_context: str = ""
    glossary: dict[str, str] | None = None


@dataclass
class LanguageDetectionResult:
    language_code: str
    language_name: str
    confidence: float | None = None


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
    def detect_language(
        self,
        texts: list[str],
    ) -> LanguageDetectionResult:
        ...

    def translate(
        self,
        texts: list[str],
        ctx: TranslationContext,
    ) -> list[str]:
        ...


ProgressCallback = Callable[[TranslationProgress], None]


LANGUAGE_NAMES = {
    "auto": "Tự động nhận diện",
    "zh": "Tiếng Trung",
    "ja": "Tiếng Nhật",
    "ko": "Tiếng Hàn",
    "en": "Tiếng Anh",
    "vi": "Tiếng Việt",
    "th": "Tiếng Thái",
    "id": "Tiếng Indonesia",
    "fr": "Tiếng Pháp",
    "de": "Tiếng Đức",
    "es": "Tiếng Tây Ban Nha",
    "pt": "Tiếng Bồ Đào Nha",
    "ru": "Tiếng Nga",
}


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


def language_display_name(code: str) -> str:
    return LANGUAGE_NAMES.get(
        code.lower(),
        code,
    )


def build_prompt(
    texts: list[str],
    ctx: TranslationContext,
) -> str:
    source = (
        "tự động nhận diện"
        if ctx.source_language == "auto"
        else language_display_name(
            ctx.source_language
        )
    )

    target = language_display_name(
        ctx.target_language
    )

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
        "Bạn là biên dịch viên subtitle chuyên nghiệp.\n"
        f"Ngôn ngữ nguồn: {source}.\n"
        f"Ngôn ngữ đích: {target}.\n"
        f"Yêu cầu phong cách: {style}.\n"
        "Giữ nguyên thứ tự số dòng.\n"
        "Chỉ trả lại các câu dịch tương ứng.\n"
        "Không giải thích.\n"
        "Không tạo timestamp.\n"
        f"Ngữ cảnh thêm: {ctx.extra_context or 'không có'}."
        f"{glossary_text}\n\n"
        f"{numbered}"
    )


def _is_valid_translation(
    text: str | None,
) -> bool:
    return bool(
        text and text.strip()
    )


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
        percentage = (
            (completed / total) * 100.0
            if total > 0
            else 0.0
        )

        progress = TranslationProgress(
            completed=completed,
            total=total,
            percentage=percentage,
            batch_number=batch_number,
            total_batches=total_batches,
            current_line=current_line,
            failed_lines=list(
                failed_lines or []
            ),
            message=message,
        )

        if self.progress_callback:
            self.progress_callback(
                progress
            )

    def detect_language(
        self,
        lines: list[SubtitleLine],
    ) -> LanguageDetectionResult:
        texts = [
            line.original.strip()
            for line in lines
            if line.original.strip()
        ]

        if not texts:
            return LanguageDetectionResult(
                language_code="auto",
                language_name="Không có dữ liệu",
                confidence=0.0,
            )

        sample = texts[:20]

        result = self.provider.detect_language(
            sample
        )

        return result

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
        for attempt in range(
            1,
            max_retries + 2,
        ):
            self._report(
                completed=completed,
                total=total,
                batch_number=batch_number,
                total_batches=total_batches,
                current_line=line.index,
                failed_lines=failed_lines,
                message=(
                    f"Retry dòng #{line.index} "
                    f"({attempt}/{max_retries + 1})"
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

                if not _is_valid_translation(
                    translated
                ):
                    continue

                line.translated = translated.strip()
                line.status = "translated"

                return True

            except Exception:
                continue

        line.status = "translation_failed"

        if line.index not in failed_lines:
            failed_lines.append(
                line.index
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
            raise ValueError(
                "batch_size phải lớn hơn 0."
            )

        if max_retries < 0:
            raise ValueError(
                "max_retries không được âm."
            )

        total = len(lines)

        if total == 0:
            return []

        total_batches = (
            total + batch_size - 1
        ) // batch_size

        failures: list[int] = []
        completed = 0

        self._report(
            completed=0,
            total=total,
            batch_number=0,
            total_batches=total_batches,
            message=(
                f"Bắt đầu dịch {total} dòng."
            ),
        )

        for batch_index, start in enumerate(
            range(0, total, batch_size),
            start=1,
        ):
            batch = lines[
                start:start + batch_size
            ]

            self._report(
                completed=completed,
                total=total,
                batch_number=batch_index,
                total_batches=total_batches,
                failed_lines=failures,
                message=(
                    f"Batch {batch_index}/"
                    f"{total_batches}: "
                    f"dòng #{batch[0].index}"
                    f" → #{batch[-1].index}"
                ),
            )

            try:
                translated = (
                    self.provider.translate(
                        [
                            line.original
                            for line in batch
                        ],
                        ctx,
                    )
                )

                if len(translated) != len(
                    batch
                ):
                    raise ValueError(
                        "Số lượng bản dịch "
                        "không khớp."
                    )

                for line, text in zip(
                    batch,
                    translated,
                ):
                    if _is_valid_translation(
                        text
                    ):
                        line.translated = (
                            text.strip()
                        )
                        line.status = (
                            "translated"
                        )
                        completed += 1
                    else:
                        success = (
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
                        )

                        if success:
                            completed += 1

                    self._report(
                        completed=completed,
                        total=total,
                        batch_number=batch_index,
                        total_batches=total_batches,
                        current_line=line.index,
                        failed_lines=failures,
                        message=(
                            f"Dòng #{line.index}"
                            ": "
                            f"{line.status}"
                        ),
                    )

            except Exception:
                self._report(
                    completed=completed,
                    total=total,
                    batch_number=batch_index,
                    total_batches=total_batches,
                    failed_lines=failures,
                    message=(
                        f"Batch {batch_index}/"
                        f"{total_batches} lỗi. "
                        "Retry từng dòng."
                    ),
                )

                for line in batch:
                    success = (
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
                f"Hoàn tất {completed}/"
                f"{total} dòng. "
                f"Lỗi: "
                f"{', '.join(map(str, failures))}"
                if failures
                else (
                    f"Hoàn tất {completed}/"
                    f"{total} dòng. "
                    "Không có lỗi."
                )
            ),
        )

        return failures
