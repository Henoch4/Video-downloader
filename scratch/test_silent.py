import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, r'C:\Users\Henoch\Documents\Programming Folder\video-downloader')
from app import probe_streams, reencode_to_h264

failures = []


def check(name, ok, detail=''):
    print(f'{"PASS" if ok else "FAIL"}: {name} {detail}')
    if not ok:
        failures.append(name)


tmp = tempfile.mkdtemp(prefix='silent_')

# --- unit 1: silent h264 -> probe detects missing audio
s1 = os.path.join(tmp, 'silent_h264.mp4')
subprocess.run(['ffmpeg', '-y', '-f', 'lavfi', '-i', 'color=black:size=64x64:rate=10',
                '-t', '1', '-c:v', 'libx264', s1], check=True, capture_output=True)
v, a = probe_streams(s1)
check('probe: silent h264 -> (h264, None)', v == 'h264' and a is None, repr((v, a)))

# --- unit 2: silent non-h264 -> reencode survives no-audio input
s2 = os.path.join(tmp, 'silent_mpeg4.mp4')
subprocess.run(['ffmpeg', '-y', '-f', 'lavfi', '-i', 'color=black:size=64x64:rate=10',
                '-t', '1', '-c:v', 'mpeg4', s2], check=True, capture_output=True)
v, a = probe_streams(s2)
check('probe: silent mpeg4 -> (mpeg4, None)', v == 'mpeg4' and a is None, repr((v, a)))
try:
    out = reencode_to_h264(s2)
    v2, a2 = probe_streams(out)
    check('reencode silent source -> h264, no crash', v2 == 'h264', repr((v2, a2)))
except subprocess.CalledProcessError as e:
    check('reencode silent source -> h264, no crash', False, e.stderr.decode(errors='replace')[:300])

# --- unit 3: source with audio -> probe finds it
s3 = os.path.join(tmp, 'with_audio.mp4')
subprocess.run(['ffmpeg', '-y', '-f', 'lavfi', '-i', 'color=red:size=64x64:rate=10',
                '-f', 'lavfi', '-i', 'sine=frequency=440',
                '-t', '1', '-c:v', 'libx264', '-c:a', 'aac', s3], check=True, capture_output=True)
v, a = probe_streams(s3)
check('probe: with audio -> aac present', v == 'h264' and a == 'aac', repr((v, a)))

# --- live: soon-Policy URL -> download succeeds WITH X-Warning header
def soon_policy():
    payload = {'Statement': [{'Condition': {'AWS:EpochTime': str(int(time.time()) + 600)}}]}
    raw = json.dumps(payload).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')

url = f'https://youtu.be/BThCK0HF1Dw?si=wGdwe8Ot0l8k-EQz&Policy={soon_policy()}'
payload = json.dumps({'url': url, 'format': 'mp4', 'quality': 'auto',
                      'job_id': 'test-warn'}).encode()
req = urllib.request.Request('http://127.0.0.1:5000/download', data=payload,
                             headers={'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req, timeout=300) as r:
        data = r.read(1024)
        warn = r.headers.get('X-Warning')
        ctype = r.headers.get('Content-Type', '')
except urllib.error.HTTPError as e:
    check('warn URL -> 200', False, f'{e.code} {e.read().decode(errors="replace")[:200]}')
else:
    check('warn URL -> 200 video/mp4', ctype == 'video/mp4', ctype)
    check('X-Warning header present', bool(warn), repr(warn))
    check('X-Warning mentions expiry', bool(warn) and 'expire' in warn.lower(), repr(warn))

print('FAILURES:', failures if failures else 'none')
sys.exit(1 if failures else 0)
