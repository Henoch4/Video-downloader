import json
import os
import re
import subprocess
import sys
import time
import urllib.request

url = 'http://127.0.0.1:5000/download'
payload = json.dumps({
    'url': 'https://youtu.be/BThCK0HF1Dw?si=wGdwe8Ot0l8k-EQz',
    'format': 'mp3',
}).encode()

req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=600) as r:
        ctype = r.headers.get('Content-Type', '')
        disp = r.headers.get('Content-Disposition', '')
        out = os.path.join(os.environ['USERPROFILE'], 'Downloads', 'endpoint_test_output.mp3')
        with open(out, 'wb') as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
except Exception as e:
    body = ''
    if hasattr(e, 'read'):
        try:
            body = e.read().decode(errors='replace')
        except Exception:
            pass
    print(f'HTTP ERROR: {e} {body}')
    sys.exit(1)

elapsed = time.time() - t0
size = os.path.getsize(out)

p = subprocess.run(['ffmpeg', '-i', out], capture_output=True, text=True, errors='replace')
audio = re.search(r'Audio:\s*([a-z0-9_]+)', p.stderr)
audio_codec = audio.group(1) if audio else None
video = re.search(r'Video:\s*([a-z0-9_]+)', p.stderr)

print(f'HTTP 200, content-type={ctype}')
print(f'content-disposition={disp}')
print(f'size={size} bytes, elapsed={elapsed:.1f}s')
print(f'audio_codec={audio_codec}, video_stream={"yes" if video else "no"}')
print('PASS' if ctype == 'audio/mpeg'
      and 'filename=' in disp and disp.lower().endswith('.mp3"')
      and audio_codec == 'mp3' and not video and size > 500000
      else 'FAIL')
