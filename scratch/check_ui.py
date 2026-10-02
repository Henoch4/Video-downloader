import urllib.request
import re

r = urllib.request.urlopen('http://127.0.0.1:5000/', timeout=10)
body = r.read().decode()
out = []
out.append('HTTP ' + str(r.status))
m = re.search(r'<title>(.*?)</title>', body)
out.append('Title: ' + (m.group(1) if m else 'NONE'))
for probe in ['useplinth.xyz', 'web3flutter.dev', 'trimmy.xyz', 'dataset.type', '1,000+ sites supported']:
    out.append(('FOUND ' if probe in body else 'MISSING ') + probe)
out.append('old youtu.be placeholder: ' + ('PRESENT' if 'youtu.be/...' in body else 'gone'))
out.append('old YouTube title: ' + ('PRESENT' if 'YouTube Downloader & Converter</title>' in body else 'gone'))
text = '\n'.join(out)
with open(r'C:\Users\Henoch\Documents\Programming Folder\video-downloader\ui_check.txt', 'w') as f:
    f.write(text)
