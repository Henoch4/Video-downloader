import json
import os
import sys
import time
import urllib.request

url = 'http://127.0.0.1:5000/download'
payload = json.dumps({
    'url': 'https://x.com/codr_1/status/2105265191986598158/video/1',
    'format': 'mp4',
}).encode()

req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=300) as r:
        ctype = r.headers.get('Content-Type', '')
        disp = r.headers.get('Content-Disposition', '')
        out = os.path.join(os.environ['USERPROFILE'], 'Downloads', 'x_test_output.mp4')
        with open(out, 'wb') as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        elapsed = time.time() - t0
        print(f'HTTP 200, content-type={ctype}')
        print(f'content-disposition={disp}')
        print(f'size={os.path.getsize(out)} bytes, elapsed={elapsed:.1f}s')
except urllib.error.HTTPError as e:
    body = e.read().decode(errors='replace')
    print(f'HTTP {e.code}: {body}')
    sys.exit(1)
except Exception as e:
    print(f'CONNECTION ERROR after {time.time() - t0:.1f}s: {e}')
    sys.exit(1)
print('DONE')
