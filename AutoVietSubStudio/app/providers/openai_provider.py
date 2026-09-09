from __future__ import annotations

import os
import re
import logging

from .base import BaseProvider
from app.core.translation import (
    TranslationContext,
    LanguageDetectionResult,
    build_prompt,
)


logger = logging.getLogger(__name__)


class OpenAITranslationProvider(BaseProvider):
    """OpenAI API-based translation and language detection provider."""

    name = "OpenAI API"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-3.5-turbo",
    ):
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key. Falls back to OPENAI_API_KEY env var.
            model: Model name (default: gpt-3.5-turbo).
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self._client = None
        self._error_reason = None

        # Try to import and initialize OpenAI client
        if self.api_key:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self.api_key)
            except ImportError:
                self._error_reason = "openai package not installed"
                logger.warning(self._error_reason)
            except Exception as e:
                self._error_reason = f"OpenAI init failed: {str(e)}"
                logger.warning(self._error_reason)
        else:
            self._error_reason = "OPENAI_API_KEY not configured"

    def available(self) -> bool:
        """Return True if provider is available."""
        return self._client is not None

    def detect_language(
        self,
        texts: list[str],
    ) -> LanguageDetectionResult:
        """
        Detect language of texts using OpenAI API.

        Args:
            texts: List of text samples to detect.

        Returns:
            LanguageDetectionResult with language code, name, and confidence.

        Raises:
            RuntimeError: If provider not available or API fails.
        """
        if not self.available():
            raise RuntimeError(
                f"OpenAI provider not available: {self._error_reason}"
            )

        if not texts:
            return LanguageDetectionResult(
                language_code="auto",
                language_name="No data",
                confidence=0.0,
            )

        # Use first sample for detection
        sample = texts[0]

        prompt = (
            "Detect the language of this text. "
            "Reply ONLY with language code (e.g., 'en', 'vi', 'zh', 'ja'). "
            "Then confidence (0-100). "
            "Format: CODE=en\nCONFIDENCE=95\n\n"
            f"Text: {sample}"
        )

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a language detection assistant."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=50,
                temperature=0.0,
            )

            result_text = response.choices[0].message.content.strip()

            # Parse response: CODE=xx\nCONFIDENCE=yy
            code = "auto"
            confidence = 0.0

            for line in result_text.split("\n"):
                if line.startswith("CODE="):
                    code = line.replace("CODE=", "").strip().lower()
                elif line.startswith("CONFIDENCE="):
                    try:
                        confidence = float(line.replace("CONFIDENCE=", "").strip()) / 100.0
                    except (ValueError, ZeroDivisionError):
                        confidence = 0.0

            # Map code to language name
            language_names = {
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

            language_name = language_names.get(code, code)

            return LanguageDetectionResult(
                language_code=code,
                language_name=language_name,
                confidence=confidence,
            )

        except Exception as e:
            raise RuntimeError(f"Language detection failed: {str(e)}") from e

    def translate(
        self,
        texts: list[str],
        ctx: TranslationContext,
    ) -> list[str]:
        """
        Translate texts using OpenAI API.

        Args:
            texts: List of texts to translate.
            ctx: Translation context with language and mode info.

        Returns:
            List of translated texts in same order.

        Raises:
            RuntimeError: If provider not available or API fails.
            ValueError: If output doesn't match input count.
        """
        if not self.available():
            raise RuntimeError(
                f"OpenAI provider not available: {self._error_reason}"
            )

        if not texts:
            return []

        # Build prompt
        prompt = build_prompt(texts, ctx)

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional subtitle translator.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )

            result_text = response.choices[0].message.content.strip()

            if not result_text:
                raise RuntimeError("AI returned empty translation")

            # Parse output: numbered lines or plain lines
            lines = []
            for raw_line in result_text.split("\n"):
                raw_line = raw_line.strip()

                # Remove number prefix (1. , 1) , 1: , etc)
                raw_line = re.sub(r"^\s*\d+[\).:\-]\s*", "", raw_line)

                if raw_line:
                    lines.append(raw_line)

            # Validate line count
            if len(lines) != len(texts):
                raise ValueError(
                    f"Translation line count mismatch: "
                    f"expected {len(texts)}, got {len(lines)}"
                )

            return lines

        except Exception as e:
            raise RuntimeError(f"Translation failed: {str(e)}") from e
