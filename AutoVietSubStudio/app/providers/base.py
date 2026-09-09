from __future__ import annotations

from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """Base provider interface for translation, language detection, etc."""

    name: str = "Base"

    @abstractmethod
    def available(self) -> bool:
        """Return True if provider is available and ready to use."""
        return False
