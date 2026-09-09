from app.core.models import SubtitleLine
from app.core.srt import validate_alignment

def test_alignment():
    a=[SubtitleLine(1,0,1000,'A'),SubtitleLine(2,1000,2000,'B')]
    b=[SubtitleLine(1,0,1000,'A','X'),SubtitleLine(2,1000,2000,'B','Y')]
    ok,bad=validate_alignment(a,b)
    assert ok and bad==[]

def test_bad_line_only():
    a=[SubtitleLine(1,0,1000,'A'),SubtitleLine(2,1000,2000,'B')]
    b=[SubtitleLine(1,0,1000,'A','X'),SubtitleLine(2,1000,2000,'B','')]
    ok,bad=validate_alignment(a,b)
    assert not ok and bad==[2]
