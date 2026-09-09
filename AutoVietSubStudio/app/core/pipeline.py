from __future__ import annotations
from dataclasses import dataclass
import logging, shutil, subprocess
from pathlib import Path
from .models import Project
from .srt import write_srt

STEPS=["Analyze","Subtitle","Translate","Validate","TTS","Sync","Video","Render","Validate Output"]

@dataclass
class PipelineResult:
    ok: bool
    step: str
    message: str

class Pipeline:
    def __init__(self, project: Project, logger=None):
        self.project=project
        self.logger=logger or logging.getLogger("autovietsub.pipeline")

    def run(self, start_step=0):
        for i,step in enumerate(STEPS[start_step:],start=start_step):
            self.logger.info("Pipeline step %s/%s: %s", i+1, len(STEPS), step)
            self.project.checkpoints[step]=True
            yield i,step
        yield len(STEPS),"DONE"


def find_ffmpeg() -> str | None:
    local=Path(__file__).resolve().parents[2]/"bin"/"ffmpeg.exe"
    if local.exists(): return str(local)
    return shutil.which("ffmpeg")

def render_video(input_path: str, output_path: str, ffmpeg: str | None=None, aspect_ratio="16:9") -> None:
    ffmpeg=ffmpeg or find_ffmpeg()
    if not ffmpeg: raise RuntimeError("Không tìm thấy FFmpeg. Hãy đặt ffmpeg.exe trong bin/ hoặc PATH.")
    vf=[]
    if aspect_ratio=="9:16": vf.append("scale=ih*9/16:ih:force_original_aspect_ratio=increase,crop=ih*9/16:ih")
    elif aspect_ratio=="1:1": vf.append("scale=ih:ih:force_original_aspect_ratio=increase,crop=ih:ih")
    elif aspect_ratio=="4:5": vf.append("scale=ih*4/5:ih:force_original_aspect_ratio=increase,crop=ih*4/5:ih")
    cmd=[ffmpeg,"-y","-i",input_path]
    if vf: cmd += ["-vf",",".join(vf)]
    cmd += ["-c:v","libx264","-preset","medium","-crf","20","-c:a","aac",output_path]
    subprocess.run(cmd,check=True)
