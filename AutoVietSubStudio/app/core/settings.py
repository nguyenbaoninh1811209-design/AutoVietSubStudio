from __future__ import annotations
from pathlib import Path
import json
DEFAULTS={
    "language":"vi","data_root":"","output_dir":"","performance_mode":"Balanced","theme":"dark",
    "translation_mode":"Bình thường","translation_model":"gpt-5-mini","openai_api_key":"",
}
class SettingsStore:
    def __init__(self,path:Path): self.path=path; self.path.parent.mkdir(parents=True,exist_ok=True)
    def load(self):
        if not self.path.exists(): return dict(DEFAULTS)
        try: return {**DEFAULTS,**json.loads(self.path.read_text(encoding='utf-8'))}
        except Exception: return dict(DEFAULTS)
    def save(self,data):
        tmp=self.path.with_suffix('.tmp'); tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8'); tmp.replace(self.path)
