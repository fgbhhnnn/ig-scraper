import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json, os, tempfile
from unittest import mock
import pytest
from igscraper import vai

RESP = {"language_code": "en", "language_probability": 0.98, "text": "Hello world! This is our new mold. Want one? (laughter)",
        "words": [
            {"text": "Hello", "start": 0.0, "end": 0.4, "type": "word", "speaker_id": "speaker_0", "logprob": -0.1},
            {"text": " ", "start": 0.4, "end": 0.45, "type": "spacing", "speaker_id": "speaker_0", "logprob": 0},
            {"text": "world!", "start": 0.45, "end": 0.9, "type": "word", "speaker_id": "speaker_0", "logprob": -0.1},
            {"text": " ", "type": "spacing", "speaker_id": "speaker_0", "logprob": 0},
            {"text": "This", "start": 1.0, "end": 1.2, "type": "word", "speaker_id": "speaker_0", "logprob": -0.1},
            {"text": " ", "type": "spacing", "logprob": 0},
            {"text": "is", "start": 1.2, "end": 1.3, "type": "word", "speaker_id": "speaker_0", "logprob": -0.1},
            {"text": " ", "type": "spacing", "logprob": 0},
            {"text": "our", "start": 1.3, "end": 1.5, "type": "word", "speaker_id": "speaker_0", "logprob": -0.1},
            {"text": " ", "type": "spacing", "logprob": 0},
            {"text": "new", "start": 1.5, "end": 1.7, "type": "word", "speaker_id": "speaker_0", "logprob": -0.1},
            {"text": " ", "type": "spacing", "logprob": 0},
            {"text": "mold", "start": 1.7, "end": 2.0, "type": "word", "speaker_id": "speaker_0", "logprob": -0.1},
            {"text": "Want", "start": 4.0, "end": 4.2, "type": "word", "speaker_id": "speaker_0", "logprob": -0.1},
            {"text": " one?", "start": 4.2, "end": 4.6, "type": "word", "speaker_id": "speaker_0", "logprob": -0.1},
            {"text": "(laughter)", "start": 5.0, "end": 5.6, "type": "audio_event", "speaker_id": "speaker_1", "logprob": -0.1},
        ]}

def test_form_defaults():
    d = vai.el_form('', '')
    assert d['model_id'] == 'scribe_v2' and d['timestamps_granularity'] == 'word' and 'language_code' not in d
    assert vai.el_form('scribe_v1', 'zh')['language_code'] == 'zh'

def test_lines_aggregate():
    L = vai.el_lines(RESP)
    assert [l['text'] for l in L] == ['Hello world!', 'This is our new mold', 'Want one?', '(laughter)']  # 停顿>0.8s 断句、句末标点断句、说话人切换断句
    assert L[1]['start'] == 1.0 and L[1]['end'] == 2.0
    txt, lang = vai.el_parse(RESP)
    assert lang == 'en' and txt.splitlines()[0] == '[0:00.0-0:00.9] 说话人0: Hello world!'
    assert '[0:05.0-0:05.6] 说话人1: (laughter)' in txt

def test_parse_fallbacks():
    assert vai.el_parse({'text': ' hi ', 'words': []}) == ('hi', '')
    multi = {'transcripts': [{'language_code': 'en', 'text': 'b', 'words': [{'text': 'b.', 'start': 2, 'end': 2.5, 'type': 'word'}]},
                             {'language_code': 'en', 'text': 'a', 'words': [{'text': 'a.', 'start': 0, 'end': 0.5, 'type': 'word'}]}]}
    txt, _ = vai.el_parse(multi)
    assert txt.splitlines() == ['[0:00.0-0:00.5] a.', '[0:02.0-0:02.5] b.']
    assert vai.el_parse({'text': '', 'words': []})[0] == ''

def test_long_split():
    ws = [{'text': f'w{i} ', 'start': i * 0.5, 'end': i * 0.5 + 0.4, 'type': 'word'} for i in range(40)]
    L = vai.el_lines({'words': ws})
    assert len(L) > 1 and all(l['end'] - l['start'] <= 8.5 for l in L)

@pytest.mark.parametrize('status,body,kind', [
    (400, {"detail": {"type": "authentication_error", "code": "invalid_api_key", "message": "API key is invalid.", "status": "invalid_api_key"}}, 'key'),
    (401, {"detail": {"code": "unauthorized", "message": "Neither authorization header nor xi-api-key received"}}, 'key'),
    (401, {"detail": {"status": "quota_exceeded", "message": "This request exceeds your quota."}}, 'key'),
    (429, {"detail": {"status": "too_many_concurrent_requests", "message": "slow down"}}, 'quota'),
    (402, {"detail": {"message": "payment required"}}, 'quota'),
    (422, {"detail": [{"loc": ["body", "file"], "msg": "field required", "type": "missing"}]}, 'other'),
])
def test_errors(status, body, kind):
    k, msg = vai.el_err(status, json.dumps(body))
    assert k == kind and 'ElevenLabs' in msg or k == 'nospeech'

class R:
    def __init__(s, code, j): s.status_code = code; s._j = j; s.text = json.dumps(j)
    def json(s): return s._j

def test_request_building(tmp_path):
    p = tmp_path / 'a.mp3'; p.write_bytes(b'x' * 3000)
    with mock.patch.object(vai.requests, 'post', return_value=R(200, RESP)) as m, mock.patch.object(vai, '_proxies', return_value={'https': 'http://127.0.0.1:7890'}):
        out = vai.el_transcribe(' sk_test ', 'scribe_v2', str(p), 'en')
    a, kw = m.call_args
    assert a[0] == 'https://api.elevenlabs.io/v1/speech-to-text'
    assert kw['headers'] == {'xi-api-key': 'sk_test'} and 'Authorization' not in kw['headers']
    assert kw['data']['model_id'] == 'scribe_v2' and kw['data']['language_code'] == 'en'
    assert kw['files']['file'][0] == 'a.mp3' and kw['files']['file'][2] == 'audio/mpeg'
    assert kw['proxies'] == {'https': 'http://127.0.0.1:7890'}
    assert out == RESP

def test_transcribe_error(tmp_path):
    p = tmp_path / 'a.mp3'; p.write_bytes(b'x' * 3000)
    with mock.patch.object(vai.requests, 'post', return_value=R(400, {"detail": {"code": "invalid_api_key", "message": "API key is invalid."}})):
        with pytest.raises(vai.STTError) as e: vai.el_transcribe('sk_x', '', str(p))
    assert e.value.kind == 'key'

def test_provider_compat():
    assert vai.stt_provider({'ai_stt_model': 'whisper-1'}) == 'openai'
    assert vai.stt_provider({'ai_stt_model': ''}) == 'off'
    assert vai.stt_provider({'ai_stt_provider': 'elevenlabs'}) == 'elevenlabs'

def test_do_stt_skips_gracefully(tmp_path):
    (tmp_path / 'a.mp3').write_bytes(b'x' * 2000)
    t = vai.AnalyzeTask(); logs = []; t.log = logs.append
    with mock.patch.object(vai.frames, 'extract_audio', return_value=str(tmp_path / 'a.mp3')), \
         mock.patch.object(vai, 'el_transcribe', side_effect=vai.STTError('ElevenLabs 额度不足', 429, 'quota')):
        assert t.do_stt({'ai_stt_provider': 'elevenlabs', 'el_key': 'sk_x'}, '', '', 'v.mp4', str(tmp_path), True) == ''
    assert '口播转写跳过' in logs[-1]
    with mock.patch.object(vai.frames, 'extract_audio', return_value=str(tmp_path / 'a.mp3')), \
         mock.patch.object(vai, 'el_transcribe', return_value=RESP):
        out = t.do_stt({'ai_stt_provider': 'elevenlabs', 'el_key': 'sk_x'}, '', '', 'v.mp4', str(tmp_path), True)
    assert out.startswith('[0:00.0-') and '4 句' in logs[-1]
    assert t.do_stt({'ai_stt_provider': 'elevenlabs', 'el_key': ''}, '', '', 'v', str(tmp_path), True) == ''

def test_prompt_mentions_alignment():
    s = vai.meta_text({'platform': 'tiktok', 'duration': 10}, [], '[0:00.0-0:00.9] Hello')
    assert '对齐' in s and '[0:00.0-0:00.9] Hello' in s
