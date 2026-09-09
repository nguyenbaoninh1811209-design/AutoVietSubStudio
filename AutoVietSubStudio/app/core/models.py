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
    source_language: str = "auto"
    target_language: str = "vi"
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
        """
        Load project from dict with safe deserialization.

        Handles:
        - Old project format (backward compatibility)
        - Missing fields (use defaults)
        - Unknown fields (ignore)
        - Type mismatches (coerce or skip)
        - Blur regions deserialization
        - Subtitle fields deserialization
        """
        # Extract and process settings
        raw_settings = data.get("settings", {})

        # Safely deserialize blur_regions
        blur_regions = []
        for item in raw_settings.get("blur_regions", []):
            if isinstance(item, dict):
                try:
                    blur_regions.append(BlurRegion(**item))
                except TypeError:
                    # Skip malformed blur regions
                    pass

        # Prepare settings data with safe defaults
        settings_data = dict(raw_settings)
        settings_data["blur_regions"] = blur_regions

        # Safely create ProjectSettings
        settings = ProjectSettings(**{
            k: v for k, v in settings_data.items()
            if k in ProjectSettings.__dataclass_fields__
        })

        # Safely deserialize subtitles
        subtitles = []
        for item in data.get("subtitles", []):
            if isinstance(item, dict):
                try:
                    subtitles.append(SubtitleLine(**item))
                except TypeError:
                    # Skip malformed subtitle lines
                    pass

        # Build project with safe field extraction
        return Project(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", "Untitled Project"),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            video_path=data.get("video_path", ""),
            subtitle_path=data.get("subtitle_path", ""),
            subtitles=subtitles,
            settings=settings,
            checkpoints=data.get("checkpoints", {}),
        )


class ProjectStore:
    """Store and load projects with atomic operations and backup support."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, project: Project) -> Path:
        return self.root / f"{project.id}.json"

    def backup_path_for(self, project: Project) -> Path:
        return self.root / f"{project.id}.json.bak"

    def save(self, project: Project) -> Path:
        """
        Save project with atomic write and backup.

        1. Write to temp file first
        2. Back up old file if exists
        3. Atomic rename temp -> main
        """
        project.touch()

        path = self.path_for(project)
        temp_path = path.with_suffix(".json.tmp")
        backup_path = self.backup_path_for(project)

        payload = json.dumps(
            project.to_dict(),
            ensure_ascii=False,
            indent=2,
        )

        # Write to temp file
        temp_path.write_text(payload, encoding="utf-8")

        # Back up old file
        if path.exists():
            try:
                backup_path.write_bytes(path.read_bytes())
            except OSError:
                pass

        # Atomic replace
        os.replace(temp_path, path)

        return path

    def load(self, path: Path) -> Project:
        """
        Load project with fallback to backup.

        1. Try to load main file
        2. If fails, try backup file
        3. If both fail, raise exception
        """
        path = Path(path)

        try:
            return Project.from_dict(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            backup_path = Path(f"{path}.bak")

            if backup_path.exists():
                try:
                    return Project.from_dict(
                        json.loads(backup_path.read_text(encoding="utf-8"))
                    )
                except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                    pass

            raise

    def recover(self, project_id: str) -> Project | None:
        """
        Try to recover project from main or backup file.

        Returns None if both fail.
        """
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
        """List all projects with (name, path) tuples."""
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
