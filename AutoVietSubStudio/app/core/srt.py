from __future__ import annotations
import re
from .models import SubtitleLine

TIME_RE = re.compile(r"^(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})$")

def to_ms(h,m,s,ms):
    return (((int(h)*60)+int(m))*60+int(s))*1000+int(ms)

def from_ms(ms: int) -> str:
    ms=max(0,int(ms)); h,rem=divmod(ms,3600000); m,rem=divmod(rem,60000); s,ms=divmod(rem,1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def parse_srt(text: str) -> list[SubtitleLine]:
    blocks = re.split(r"\n\s*\n", text.replace("\r\n","\n").replace("\r","\n").strip())
    result=[]
    for block in blocks:
        lines=block.split("\n")
        if len(lines)<3: continue
        try: idx=int(lines[0].strip())
        except ValueError: continue
        m=TIME_RE.match(lines[1].strip())
        if not m: continue
        start=to_ms(*m.groups()[:4]); end=to_ms(*m.groups()[4:])
        result.append(SubtitleLine(index=idx,start_ms=start,end_ms=end,original="\n".join(lines[2:]).strip()))
    return result

def write_srt(lines: list[SubtitleLine], use_translated=True) -> str:
    out=[]
    for line in lines:
        text=line.translated if use_translated else line.original
        if text is None: text=""
        out.append(str(line.index)); out.append(f"{from_ms(line.start_ms)} --> {from_ms(line.end_ms)}"); out.append(text); out.append("")
    return "\n".join(out)

def validate_alignment(original: list[SubtitleLine], translated: list[SubtitleLine]) -> tuple[bool, list[int]]:
    bad=[]
    if len(original)!=len(translated):
        bad=list(range(min(len(original),len(translated))+1, max(len(original),len(translated))+1))
        return False,bad
    for i,(a,b) in enumerate(zip(original,translated),1):
        if (a.index,a.start_ms,a.end_ms)!=(b.index,b.start_ms,b.end_ms) or not b.translated.strip():
            bad.append(i)
    return not bad,bad
