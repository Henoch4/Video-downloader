import json
import os
import sys
import time
import urllib.request
import zipfile

failures = []


def check(name, ok, detail=''):
    print(f'{"PASS" if ok else "FAIL"}: {name} {detail}')
    if not ok:
        failures.append(name)


payload = json.dumps({
    'url': 'https://x.com/codr_1/status/2105265191986598158/video/1',
    'format': 'mp4',
    'quality': 'auto',
    'pack': True,
    'job_id': 'test-pack',
}).encode()
req = urllib.request.Request('http://127.0.0.1:5000/download', data=payload,
                             headers={'Content-Type': 'application/json'})
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=300) as r:
        out = os.path.join(os.environ['USERPROFILE'], 'Downloads', 'pack_test.zip')
        with open(out, 'wb') as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        ctype = r.headers.get('Content-Type', '')
        cdisp = r.headers.get('Content-Disposition', '')
        warn = r.headers.get('X-Warning')
except urllib.error.HTTPError as e:
    print('HTTP', e.code, e.read().decode(errors='replace'))
    sys.exit(1)

elapsed = time.time() - t0
size = os.path.getsize(out)
print(f'  downloaded in {elapsed:.1f}s, size={size}, ctype={ctype}, disp={cdisp!r}')

check('pack -> application/zip', ctype == 'application/zip', ctype)
check('pack -> _pack.zip filename', '_pack.zip' in cdisp, cdisp)
check('pack -> no spurious warning', not warn, repr(warn))

z = zipfile.ZipFile(out)
names = z.namelist()
mp4s = [n for n in names if n.endswith('.mp4') and '_small' not in n]
smalls = [n for n in names if n.endswith('_small.mp4')]
frames = [n for n in names if '_frames/' in n and n.endswith('.jpg')]
print(f'  entries: {len(names)} (mp4={mp4s}, small={len(smalls)}, frames={len(frames)})')

check('pack -> full mp4 inside', len(mp4s) == 1, repr(mp4s))
check('pack -> _small.mp4 inside', len(smalls) == 1, repr(smalls))
check('pack -> frames inside', len(frames) >= 1, f'{len(frames)} frames')
check('pack -> f_001.jpg exists', any(n.endswith('_frames/f_001.jpg') for n in names),
      repr([n for n in names if 'frames' in n][:3]))

bad = z.testzip()
check('pack -> zip integrity', bad is None, repr(bad))

# small mp4 must be h264 and playable
if smalls:
    small_path = z.extract(smalls[0], os.path.join(os.environ['USERPROFILE'], 'Downloads', 'pack_extract'))
    import subprocess
    p = subprocess.run(['ffmpeg', '-i', small_path], capture_output=True, text=True, errors='replace')
    check('pack -> _small.mp4 is h264', 'Video: h264' in p.stderr, p.stderr.splitlines()[0] if p.stderr else '')

print('FAILURES:', failures if failures else 'none')
sys.exit(1 if failures else 0)
