from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
from .models import SubtitleLine

@dataclass
class TranslationContext:
    mode: str = "Bình thường"
    extra_context: str = ""
    glossary: dict[str,str] | None = None

class Translator(Protocol):
    def translate(self, texts: list[str], ctx: TranslationContext) -> list[str]: ...

MODE_PROMPTS={
    "Bình thường":"dịch tự nhiên, trung thành ngữ cảnh, không thêm giải thích",
    "Hài hước":"dịch tự nhiên, hài hước vừa phải, giữ đúng ý nghĩa và bối cảnh",
    "Ngôn tình":"dịch mềm mại, giàu cảm xúc, phù hợp hội thoại ngôn tình",
    "Tu tiên / huyền huyễn":"dùng thuật ngữ tu tiên/huyền huyễn tự nhiên, giữ nhất quán tên riêng và cảnh giới",
    "Trung thành nguyên tác":"ưu tiên sát nghĩa, không diễn giải quá mức",
}

def build_prompt(texts: list[str], ctx: TranslationContext) -> str:
    glossary=""
    if ctx.glossary:
        glossary="\nGlossary:\n"+"\n".join(f"- {k} => {v}" for k,v in ctx.glossary.items())
    style=MODE_PROMPTS.get(ctx.mode, MODE_PROMPTS["Bình thường"])
    numbered="\n".join(f"{i+1}. {t}" for i,t in enumerate(texts))
    return f"""Bạn là biên dịch viên subtitle chuyên nghiệp. {style}.\nGiữ nguyên thứ tự số dòng. Chỉ trả lại các câu dịch tương ứng theo đúng số dòng, không giải thích. Mỗi dòng chỉ là phần thoại. Không tự tạo timestamp.\nNgữ cảnh thêm: {ctx.extra_context or 'không có'}.{glossary}\n\n{numbered}"""

class TranslationEngine:
    def __init__(self, provider: Translator): self.provider=provider

    def translate_lines(self, lines: list[SubtitleLine], ctx: TranslationContext, batch_size=20, max_retries=2):
        failures=[]
        for start in range(0,len(lines),batch_size):
            batch=lines[start:start+batch_size]
            try:
                translated=self.provider.translate([x.original for x in batch],ctx)
            except Exception:
                failures.extend(range(start+1,start+len(batch)+1)); continue
            if len(translated)!=len(batch):
                failures.extend(range(start+1,start+len(batch)+1)); continue
            for item,text in zip(batch,translated):
                if not text or not text.strip(): failures.append(item.index)
                else: item.translated=text.strip(); item.status="translated"
        return failures
