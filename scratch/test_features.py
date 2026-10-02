import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, r'C:\Users\Henoch\Documents\Programming Folder\video-downloader')
from app import policy_info, extract_m3u8

failures = []


def check(name, ok, detail=''):
    print(f'{"PASS" if ok else "FAIL"}: {name} {detail}')
    if not ok:
        failures.append(name)


def signed(epoch):
    payload = {'Statement': [{'Condition': {'AWS:EpochTime': str(int(epoch))}}]}
    raw = json.dumps(payload).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


now = time.time()

# --- #5 policy_info units
state, msg = policy_info('https://x.com/foo')
check('no Policy -> ignored', state == '' and msg == '')

state, msg = policy_info(f'https://luna.loom.com/vod/master.m3u8?Policy={signed(now - 3600)}&Signature=abc&Key-Pair-Id=K1')
check('expired Policy -> expired', state == 'expired' and 'expired' in msg.lower(), repr(msg))

state, msg = policy_info(f'https://luna.loom.com/vod/master.m3u8?Policy={signed(now + 7200)}&Signature=abc&Key-Pair-Id=K1')
check('future Policy -> no warning (>30min)', state == '', repr((state, msg)))

state, msg = policy_info(f'https://luna.loom.com/vod/master.m3u8?Policy={signed(now + 600)}&Signature=abc&Key-Pair-Id=K1')
check('soon Policy -> warn', state == 'warn' and 'expires' in msg.lower(), repr((state, msg)))

# --- #4 extract_m3u8 units
html = '''
<html><script>
var a = "https://luna.loom.com/vod/e4bb/media-clip0-video.m3u8?Policy=p&Signature=s&Key-Pair-Id=k1";
var b = "https://luna.loom.com/vod/e4bb/master.m3u8?Policy=p\\u0026Signature=s\\u0026Key-Pair-Id=k1";
var dup = "https://luna.loom.com/vod/e4bb/master.m3u8?Policy=p&Signature=s&Key-Pair-Id=k1";
</script></html>'''
urls = extract_m3u8(html)
check('extract: finds both', len(urls) == 2, repr(urls))
check('extract: master preferred first', 'master' in urls[0], repr(urls[0]))
check('extract: \\u0026 unescaped', 'Signature=s&' in urls[0], repr(urls[0]))

# --- /progress endpoint (unknown id)
try:
    with urllib.request.urlopen('http://127.0.0.1:5000/progress/nope', timeout=5) as r:
        body = json.loads(r.read().decode())
    check('GET /progress unknown -> {}', r.status == 200 and body == {}, repr(body))
except Exception as e:
    check('GET /progress unknown -> {}', False, repr(e))

# --- #2 quality=480 download
payload = json.dumps({
    'url': 'https://youtu.be/BThCK0HF1Dw?si=wGdwe8Ot0l8k-EQz',
    'format': 'mp4',
    'quality': '480',
    'job_id': 'test-q480',
}).encode()
req = urllib.request.Request('http://127.0.0.1:5000/download', data=payload,
                             headers={'Content-Type': 'application/json'})
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=300) as r:
        out = os.path.join(os.environ['USERPROFILE'], 'Downloads', 'q480_test.mp4')
        with open(out, 'wb') as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        ctype = r.headers.get('Content-Type', '')
        warn = r.headers.get('X-Warning')
except Exception as e:
    check('quality=480 download', False, repr(e))
    print('FAILURES:', failures)
    sys.exit(1)

elapsed = time.time() - t0
p = subprocess.run(['ffmpeg', '-i', out], capture_output=True, text=True, errors='replace')
m = re.search(r'Video:.*?(\d{3,4})x(\d{3,4})', p.stderr)
height = int(m.group(2)) if m else 0
has_audio = bool(re.search(r'Audio:\s*[a-z0-9_]+', p.stderr))
size = os.path.getsize(out)
print(f'  downloaded in {elapsed:.1f}s, size={size}, {m.group(1) if m else "?"}x{height}, '
      f'audio={"yes" if has_audio else "NO"}, X-Warning={warn!r}')

check('quality=480 -> h264', 'Video: h264' in p.stderr)
check('quality=480 -> height <= 480', 0 < height <= 480, f'height={height}')
check('quality=480 -> audio present (no silent mp4)', has_audio)
check('quality=480 -> no spurious warning', not warn, repr(warn))

# --- progress recorded for the job
try:
    with urllib.request.urlopen('http://127.0.0.1:5000/progress/test-q480', timeout=5) as r:
        prog = json.loads(r.read().decode())
    check('progress hook wrote job state', 'stage' in prog, repr(prog))
except Exception as e:
    check('progress hook wrote job state', False, repr(e))

print('FAILURES:', failures if failures else 'none')
sys.exit(1 if failures else 0)
