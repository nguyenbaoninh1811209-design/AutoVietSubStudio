from __future__ import annotations
import os, re
from .base import BaseProvider
from app.core.translation import TranslationContext, build_prompt

class OpenAITranslationProvider(BaseProvider):
    name="OpenAI API"
    def __init__(self, api_key: str | None = None, model: str = "gpt-5-mini"):
        self.api_key=api_key or os.getenv("OPENAI_API_KEY")
        self.model=model
        self._client=None
        if self.api_key:
            from openai import OpenAI
            self._client=OpenAI(api_key=self.api_key)

    def available(self): return self._client is not None

    def translate(self, texts, ctx: TranslationContext):
        if not self._client: raise RuntimeError("OPENAI_API_KEY chưa được cấu hình")
        prompt=build_prompt(texts,ctx)
        resp=self._client.responses.create(model=self.model,input=prompt)
        content=getattr(resp,"output_text","").strip()
        if not content: raise RuntimeError("AI không trả về nội dung")
        lines=[]
        for raw in content.splitlines():
            raw=re.sub(r"^\s*\d+[\).:\-]\s*", "", raw).strip()
            if raw: lines.append(raw)
        return lines
