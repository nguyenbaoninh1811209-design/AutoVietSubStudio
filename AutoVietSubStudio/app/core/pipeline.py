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
        self.project.checkpoints[step] = value

    def is_completed(
        self,
        step: str,
    ) -> bool:
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

        yield end_step + 1, "DONE"

    def run_until(
        self,
        end_step: int,
    ) -> Iterator[tuple[int, str]]:
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
    }

    return filters.get(aspect_ratio)


def render_video(
    input_path: str,
    output_path: str,
    ffmpeg: str | None = None,
    aspect_ratio: str = "16:9",
) -> None:
    input_file = Path(input_path)
    output_file = Path(output_path)

    if not input_file.exists():
        raise FileNotFoundError(
            "Không tìm thấy video đầu vào: "
            f"{input_file}"
        )

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

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

    video_filter = build_aspect_filter(
        aspect_ratio
    )

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
