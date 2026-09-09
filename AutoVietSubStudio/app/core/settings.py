from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import os


DEFAULTS: dict[str, Any] = {
    "language": "vi",
    "data_root": "",
    "output_dir": "",
    "performance_mode": "Balanced",
    "theme": "dark",
    "translation_mode": "Bình thường",
    "translation_model": "gpt-5-mini",
    "openai_api_key": "",
}


class SettingsStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return dict(DEFAULTS)

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))

            if not isinstance(raw, dict):
                return dict(DEFAULTS)

            return {
                **DEFAULTS,
                **raw,
            }

        except (
            OSError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ):
            backup = self.path.with_suffix(self.path.suffix + ".bak")

            if backup.exists():
                try:
                    raw = json.loads(
                        backup.read_text(encoding="utf-8")
                    )

                    if isinstance(raw, dict):
                        return {
                            **DEFAULTS,
                            **raw,
                        }

                except (
                    OSError,
                    json.JSONDecodeError,
                    TypeError,
                    ValueError,
                ):
                    pass

            return dict(DEFAULTS)

    def save(self, data: dict[str, Any]) -> Path:
        merged = {
            **DEFAULTS,
            **data,
        }

        payload = json.dumps(
            merged,
            ensure_ascii=False,
            indent=2,
        )

        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        backup = self.path.with_suffix(self.path.suffix + ".bak")

        temp.write_text(payload, encoding="utf-8")

        if self.path.exists():
            try:
                backup.write_bytes(self.path.read_bytes())
            except OSError:
                pass

        os.replace(temp, self.path)

        return self.path

    def reset(self) -> Path:
        return self.save(dict(DEFAULTS))

    def get(self, key: str, default: Any = None) -> Any:
        return self.load().get(key, default)

    def set(self, key: str, value: Any) -> Path:
        settings = self.load()
        settings[key] = value
        return self.save(settings)
