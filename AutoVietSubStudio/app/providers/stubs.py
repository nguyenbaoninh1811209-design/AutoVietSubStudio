from __future__ import annotations
class OptionalProvider:
    def __init__(self,name,dependency_hint=""): self.name=name; self.dependency_hint=dependency_hint
    def available(self): return False
    def status(self): return f"{self.name}: optional provider chưa được cài/đấu nối ({self.dependency_hint})"

class OCRProvider(OptionalProvider): pass
class ASRProvider(OptionalProvider): pass
class TTSProvider(OptionalProvider): pass
