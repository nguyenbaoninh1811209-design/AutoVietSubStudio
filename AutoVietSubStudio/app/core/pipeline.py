from __future__ import annotations

from dataclasses import dataclass
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Iterator

from .models import Project


STEPS = [
    "Analyze",
    "Subtitle",
    "Translate",
    "Validate",
    "TTS",
    "Sync",
    "Video",
    "Render",
    "Validate Output",
]


@dataclass
class PipelineResult:
    ok: bool
    step: str
    message: str


class Pipeline:
    """Pipeline for processing video subtitle projects."""

    def __init__(
        self,
        project: Project,
        logger=None,
    ):
        self.project = project
        self.logger = (
            logger
            or logging.getLogger(
                "autovietsub.pipeline"
            )
        )

    def _mark(
        self,
        step: str,
        value: bool,
    ) -> None:
        """Mark pipeline step as completed or not."""
        self.project.checkpoints[step] = value

    def is_completed(
        self,
        step: str,
    ) -> bool:
        """Check if pipeline step is completed."""
        return bool(
            self.project.checkpoints.get(
                step,
                False,
            )
        )

    def reset_from(
        self,
        step_index: int = 0,
    ) -> None:
        """Reset all checkpoints from given step onward."""
        if (
            step_index < 0
            or step_index > len(STEPS)
        ):
            raise ValueError(
                "step_index không hợp lệ."
            )

        for step in STEPS[step_index:]:
            self._mark(step, False)

    def run(
        self,
        start_step: int = 0,
        end_step: int | None = None,
    ) -> Iterator[tuple[int, str]]:
        """
        Run pipeline from start_step to end_step (inclusive).

        Yields:
            (step_index, step_name) tuples for each step.
            Final yield is (len(STEPS), "DONE").
        """
        if (
            start_step < 0
            or start_step >= len(STEPS)
        ):
            raise ValueError(
                "start_step không hợp lệ."
            )

        if end_step is None:
            end_step = len(STEPS) - 1

        if (
            end_step < start_step
            or end_step >= len(STEPS)
        ):
            raise ValueError(
                "end_step không hợp lệ."
            )

        for index in range(
            start_step,
            end_step + 1,
        ):
            step = STEPS[index]

            if self.is_completed(step):
                self.logger.info(
                    "Bỏ qua bước đã hoàn thành "
                    "%s/%s: %s",
                    index + 1,
                    len(STEPS),
                    step,
                )

                yield index, step
                continue

            self.logger.info(
                "Pipeline step %s/%s: %s",
                index + 1,
                len(STEPS),
                step,
            )

            yield index, step

        yield len(STEPS), "DONE"

    def run_until(
        self,
        end_step: int,
    ) -> Iterator[tuple[int, str]]:
        """Run pipeline from beginning until end_step (inclusive)."""
        if (
            end_step < 0
            or end_step >= len(STEPS)
        ):
            raise ValueError(
                "end_step không hợp lệ."
            )

        return self.run(
            start_step=0,
            end_step=end_step,
        )


def find_ffmpeg() -> str | None:
    """
    Find FFmpeg executable.

    Priority:
    1. AutoVietSubStudio/bin/ffmpeg.exe
    2. System PATH
    """
    local = (
        Path(__file__).resolve().parents[2]
        / "bin"
        / "ffmpeg.exe"
    )

    if local.exists():
        return str(local)

    return shutil.which("ffmpeg")


def build_aspect_filter(
    aspect_ratio: str,
) -> str | None:
    """
    Build FFmpeg aspect ratio filter.

    Supports: 9:16, 1:1, 4:5, 4:3
    Returns None for 16:9 (keep original).

    Args:
        aspect_ratio: Aspect ratio string (e.g., "16:9").

    Returns:
        FFmpeg filter string or None.
    """
    filters = {
        "9:16": (
            "scale=ih*9/16:ih:"
            "force_original_aspect_ratio=increase,"
            "crop=ih*9/16:ih"
        ),
        "1:1": (
            "scale=ih:ih:"
            "force_original_aspect_ratio=increase,"
            "crop=ih:ih"
        ),
        "4:5": (
            "scale=ih*4/5:ih:"
            "force_original_aspect_ratio=increase,"
            "crop=ih*4/5:ih"
        ),
        "4:3": (
            "scale=iw*4/3:ih:"
            "force_original_aspect_ratio=increase,"
            "crop=iw*4/3:ih"
        ),
    }

    return filters.get(aspect_ratio)


def render_video(
    input_path: str,
    output_path: str,
    ffmpeg: str | None = None,
    aspect_ratio: str = "16:9",
) -> None:
    """
    Render video with aspect ratio conversion using FFmpeg.

    Args:
        input_path: Path to input video.
        output_path: Path to output video.
        ffmpeg: Optional path to FFmpeg executable.
        aspect_ratio: Target aspect ratio (default: 16:9).

    Raises:
        FileNotFoundError: If input video not found.
        RuntimeError: If FFmpeg not found or render fails.
    """
    input_file = Path(input_path)
    output_file = Path(output_path)

    # Check input
    if not input_file.exists():
        raise FileNotFoundError(
            "Không tìm thấy video đầu vào: "
            f"{input_file}"
        )

    # Create output directory
    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Find FFmpeg
    ffmpeg_path = (
        ffmpeg
        or find_ffmpeg()
    )

    if not ffmpeg_path:
        raise RuntimeError(
            "Không tìm thấy FFmpeg. "
            "Hãy đặt ffmpeg.exe trong bin/ "
            "hoặc thêm FFmpeg vào PATH."
        )

    # Build filter
    video_filter = build_aspect_filter(
        aspect_ratio
    )

    # Build command
    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(input_file),
    ]

    if video_filter:
        command.extend(
            [
                "-vf",
                video_filter,
            ]
        )

    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(output_file),
        ]
    )

    # Run FFmpeg
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )

    except subprocess.CalledProcessError as exc:
        detail = (
            exc.stderr
            or exc.stdout
            or ""
        ).strip()

        if len(detail) > 2000:
            detail = detail[-2000:]

        raise RuntimeError(
            "FFmpeg render thất bại.\n"
            f"{detail}"
        ) from exc
