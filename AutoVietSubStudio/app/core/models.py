from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
import json
import os
import time
import uuid


@dataclass
class SubtitleLine:
    index: int
    start_ms: int
    end_ms: int
    original: str = ""
    translated: str = ""
    confidence: float | None = None
    status: str = "pending"
    source_region: dict[str, float] | None = None


@dataclass
class BlurRegion:
    x: float
    y: float
    width: float
    height: float
    strength: int = 12


@dataclass
class ProjectSettings:
    language: str = "vi"
    translation_mode: str = "Bình thường"
    aspect_ratio: str = "16:9"
    performance_mode: str = "Balanced"
    font_family: str = "Arial"
    font_size: int = 52
    font_outline: int = 3
    voice_provider: str = "None"
    voice_name: str = ""
    data_root: str = ""
    output_dir: str = ""
    ocr_region: dict[str, float] | None = None
    subtitle_region: str = "bottom"
    blur_regions: list[BlurRegion] = field(default_factory=list)
    auto_save: bool = True


@dataclass
class Project:
    id: str
    name: str
    created_at: float
    updated_at: float
    video_path: str = ""
    subtitle_path: str = ""
    subtitles: list[SubtitleLine] = field(default_factory=list)
    settings: ProjectSettings = field(default_factory=ProjectSettings)
    checkpoints: dict[str, bool] = field(default_factory=dict)

    @staticmethod
    def new(name: str = "Untitled Project") -> "Project":
        now = time.time()
        return Project(
            id=str(uuid.uuid4()),
            name=name,
            created_at=now,
            updated_at=now,
        )

    def touch(self) -> None:
        self.updated_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Project":
        raw_settings = data.get("settings", {})

        blur_regions = [
            BlurRegion(**item)
            for item in raw_settings.get("blur_regions", [])
            if isinstance(item, dict)
        ]

        settings_data = dict(raw_settings)
        settings_data["blur_regions"] = blur_regions

        settings = ProjectSettings(**settings_data)

        subtitles = [
            SubtitleLine(**item)
            for item in data.get("subtitles", [])
            if isinstance(item, dict)
        ]

        return Project(
            id=data["id"],
            name=data["name"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            video_path=data.get("video_path", ""),
            subtitle_path=data.get("subtitle_path", ""),
            subtitles=subtitles,
            settings=settings,
            checkpoints=data.get("checkpoints", {}),
        )


class ProjectStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, project: Project) -> Path:
        return self.root / f"{project.id}.json"

    def backup_path_for(self, project: Project) -> Path:
        return self.root / f"{project.id}.json.bak"

    def save(self, project: Project) -> Path:
        project.touch()

        path = self.path_for(project)
        temp_path = path.with_suffix(".json.tmp")
        backup_path = self.backup_path_for(project)

        payload = json.dumps(
            project.to_dict(),
            ensure_ascii=False,
            indent=2,
        )

        temp_path.write_text(payload, encoding="utf-8")

        if path.exists():
            try:
                backup_path.write_bytes(path.read_bytes())
            except OSError:
                pass

        os.replace(temp_path, path)

        return path

    def load(self, path: Path) -> Project:
        path = Path(path)

        try:
            return Project.from_dict(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            backup_path = Path(f"{path}.bak")

            if backup_path.exists():
                return Project.from_dict(
                    json.loads(backup_path.read_text(encoding="utf-8"))
                )

            raise

    def recover(self, project_id: str) -> Project | None:
        path = self.root / f"{project_id}.json"
        backup_path = self.root / f"{project_id}.json.bak"

        for candidate in (path, backup_path):
            if not candidate.exists():
                continue

            try:
                return Project.from_dict(
                    json.loads(candidate.read_text(encoding="utf-8"))
                )
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue

        return None

    def list_projects(self) -> list[tuple[str, Path]]:
        items: list[tuple[str, Path]] = []

        for path in self.root.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                items.append((data.get("name", path.stem), path))
            except (OSError, json.JSONDecodeError, TypeError):
                continue

        return sorted(
            items,
            key=lambda item: item[0].lower(),
        )
