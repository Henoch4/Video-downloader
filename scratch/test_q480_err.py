import json
import sys
import urllib.request

payload = json.dumps({
    'url': 'https://youtu.be/BThCK0HF1Dw?si=wGdwe8Ot0l8k-EQz',
    'format': 'mp4',
    'quality': '480',
    'job_id': 'test-q480-retry',
}).encode()
req = urllib.request.Request('http://127.0.0.1:5000/download', data=payload,
                             headers={'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req, timeout=300) as r:
        print('OK', r.status, r.headers.get('Content-Type'), r.headers.get('Content-Disposition'))
except urllib.error.HTTPError as e:
    print('HTTP', e.code, e.read().decode(errors='replace'))
    sys.exit(1)
