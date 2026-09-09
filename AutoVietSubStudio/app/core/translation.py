from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import SubtitleLine


@dataclass
class TranslationContext:
    mode: str = "Bình thường"
    extra_context: str = ""
    glossary: dict[str, str] | None = None


class Translator(Protocol):
    def translate(
        self,
        texts: list[str],
        ctx: TranslationContext,
    ) -> list[str]:
        ...


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
    def __init__(self, provider: Translator):
        self.provider = provider

    def _translate_one(
        self,
        line: SubtitleLine,
        ctx: TranslationContext,
        max_retries: int,
    ) -> bool:
        for attempt in range(max_retries + 1):
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
                return True

            except Exception:
                if attempt >= max_retries:
                    break

        line.status = "translation_failed"
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

        failures: list[int] = []

        for start in range(0, len(lines), batch_size):
            batch = lines[start:start + batch_size]

            try:
                translated = self.provider.translate(
                    [line.original for line in batch],
                    ctx,
                )

                if len(translated) != len(batch):
                    raise ValueError(
                        "Provider trả về số lượng bản dịch "
                        "không khớp với số dòng yêu cầu."
                    )

                for line, text in zip(batch, translated):
                    if _is_valid_translation(text):
                        line.translated = text.strip()
                        line.status = "translated"
                    else:
                        if not self._translate_one(
                            line,
                            ctx,
                            max_retries,
                        ):
                            failures.append(line.index)

            except Exception:
                # Batch lỗi: chỉ retry từng dòng,
                # không bỏ cả batch.
                for line in batch:
                    if not self._translate_one(
                        line,
                        ctx,
                        max_retries,
                    ):
                        failures.append(line.index)

        return failures
