import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, r'C:\Users\Henoch\Documents\Programming Folder\video-downloader')
from app import video_codec

url = 'http://127.0.0.1:5000/download'
payload = json.dumps({'url': 'https://youtu.be/BThCK0HF1Dw?si=wGdwe8Ot0l8k-EQz'}).encode()

req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=800) as r:
        ctype = r.headers.get('Content-Type', '')
        disp = r.headers.get('Content-Disposition', '')
        out = os.path.join(os.environ['USERPROFILE'], 'Downloads', 'endpoint_test_output.mp4')
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
codec = video_codec(out)
print(f'HTTP 200, content-type={ctype}')
print(f'content-disposition={disp}')
print(f'size={size} bytes, elapsed={elapsed:.1f}s')
print(f'codec={codec}')
print('PASS' if codec == 'h264' and size > 1000000 else 'FAIL')
