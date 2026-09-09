from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
import json, time, uuid

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
        return Project(id=str(uuid.uuid4()), name=name, created_at=now, updated_at=now)

    def touch(self) -> None:
        self.updated_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Project":
        settings = ProjectSettings(**data.get("settings", {}))
        subs = [SubtitleLine(**x) for x in data.get("subtitles", [])]
        settings.blur_regions = [BlurRegion(**x) if isinstance(x, dict) else x for x in data.get("settings", {}).get("blur_regions", [])]
        return Project(
            id=data["id"], name=data["name"], created_at=data["created_at"], updated_at=data["updated_at"],
            video_path=data.get("video_path", ""), subtitle_path=data.get("subtitle_path", ""),
            subtitles=subs, settings=settings, checkpoints=data.get("checkpoints", {})
        )

class ProjectStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, project: Project) -> Path:
        return self.root / f"{project.id}.json"

    def save(self, project: Project) -> Path:
        project.touch()
        path = self.path_for(project)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(project.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    def load(self, path: Path) -> Project:
        return Project.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_projects(self) -> list[tuple[str, Path]]:
        items=[]
        for p in self.root.glob("*.json"):
            try:
                data=json.loads(p.read_text(encoding="utf-8"))
                items.append((data.get("name", p.stem), p))
            except Exception:
                continue
        return sorted(items, key=lambda x:x[0].lower())
