from app.core.srt import parse_srt, write_srt

def test_srt_roundtrip():
    s='1\n00:00:00,000 --> 00:00:01,250\nXin chao!\n\n2\n00:00:01,500 --> 00:00:02,000\nTam biet.\n'
    lines=parse_srt(s)
    assert len(lines)==2
    lines[1].translated='Tạm biệt.'
    out=write_srt(lines,True)
    assert '00:00:01,500 --> 00:00:02,000' in out
    assert 'Tạm biệt.' in out
