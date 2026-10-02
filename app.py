import base64
import json
import os
import re
import shutil
import subprocess
import time
import zipfile
import yt_dlp
from flask import Flask, render_template, request, send_file, jsonify
from urllib.parse import urlparse, parse_qs
import tempfile

app = Flask(__name__, template_folder='templates')

# Portable across Windows (local dev) and Linux (Vercel functions).
TEMP_BASE = os.path.join(tempfile.gettempdir(), 'video_converter')

# job_id -> {stage, pct, speed, eta} — written by yt-dlp progress hooks,
# read by GET /progress/<job_id> while the download request is in flight.
PROGRESS = {}


def _fresh_workdir():
    """Per-request temp dir: safe for concurrent serverless invocations.
    Purges workdirs older than 2h; each request only touches its own dir."""
    os.makedirs(TEMP_BASE, exist_ok=True)
    now = time.time()
    for name in os.listdir(TEMP_BASE):
        p = os.path.join(TEMP_BASE, name)
        try:
            if now - os.path.getmtime(p) > 7200:
                shutil.rmtree(p, ignore_errors=True)
        except OSError:
            pass
    return tempfile.mkdtemp(prefix='dl_', dir=TEMP_BASE)


def ffmpeg_exe():
    """System ffmpeg if present (local), else the bundled imageio-ffmpeg
    binary (Vercel has no ffmpeg on PATH)."""
    exe = shutil.which('ffmpeg')
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def find_downloaded_file(ydl, info):
    """yt-dlp may change the extension when merging - locate the real file."""
    for d in info.get('requested_downloads') or []:
        if d.get('filepath') and os.path.exists(d['filepath']):
            return d['filepath']
    path = ydl.prepare_filename(info)
    if os.path.exists(path):
        return path
    base = os.path.splitext(path)[0]
    for ext in ('.mp4', '.webm', '.mkv', '.m4a', '.opus', '.mp3'):
        if os.path.exists(base + ext):
            return base + ext
    return None


def probe_streams(path):
    """Return (video_codec or None, audio_codec or None)."""
    p = subprocess.run([ffmpeg_exe(), '-i', path],
                       capture_output=True, text=True, errors='replace')
    v = re.search(r'Video:\s*([a-z0-9_]+)', p.stderr)
    a = re.search(r'Audio:\s*([a-z0-9_]+)', p.stderr)
    return (v.group(1) if v else None), (a.group(1) if a else None)


def video_codec(path):
    """Video codec name (e.g. h264) or None. Kept for tests/back-compat."""
    return probe_streams(path)[0]


def reencode_to_h264(src):
    """Re-encode to H.264/AAC MP4 so it plays everywhere. Returns new path."""
    base = os.path.splitext(src)[0]
    dst = base + '.h264.mp4'
    subprocess.run([
        ffmpeg_exe(), '-y', '-i', src,
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21',
        '-c:a', 'aac', '-b:a', '192k',
        '-movflags', '+faststart',
        dst
    ], check=True, capture_output=True)
    if os.path.abspath(src) != os.path.abspath(dst):
        os.remove(src)
    return dst


def convert_to_mp3(src, title):
    """Extract audio to MP3 (highest-quality VBR) with an ID3 title tag."""
    dst = os.path.splitext(src)[0] + '.mp3'
    if os.path.abspath(src) == os.path.abspath(dst):
        return src
    subprocess.run([
        ffmpeg_exe(), '-y', '-i', src, '-vn',
        '-c:a', 'libmp3lame', '-q:a', '0',
        '-id3v2_version', '3',
        '-metadata', f'title={title}',
        dst
    ], check=True, capture_output=True)
    os.remove(src)
    return dst


def build_pack(mp4, title):
    """Analysis pack: 480p copy + 1fps frames, zipped with the full MP4."""
    stem = os.path.splitext(mp4)[0]
    small = stem + '_small.mp4'
    subprocess.run([
        ffmpeg_exe(), '-y', '-i', mp4,
        '-vf', 'scale=854:-2', '-c:v', 'libx264',
        '-crf', '28', '-preset', 'veryfast',
        '-c:a', 'aac', '-b:a', '96k',
        small
    ], check=True, capture_output=True)
    fdir = stem + '_frames'
    os.makedirs(fdir, exist_ok=True)
    subprocess.run([
        ffmpeg_exe(), '-y', '-i', mp4,
        '-vf', 'fps=1', '-q:v', '2',
        os.path.join(fdir, 'f_%03d.jpg')
    ], check=True, capture_output=True)
    zpath = stem + '_pack.zip'
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(mp4, os.path.basename(mp4))
        z.write(small, os.path.basename(small))
        for name in sorted(os.listdir(fdir)):
            z.write(os.path.join(fdir, name),
                    os.path.join(os.path.basename(fdir), name))
    return zpath


def video_format(max_height=None):
    """yt-dlp format chain; height-capped when a quality is selected."""
    h = f'[height<={max_height}]' if max_height else ''
    return (f'bestvideo{h}[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/'
            f'bestvideo{h}[ext=mp4]+bestaudio/'
            f'bestvideo{h}+bestaudio/'
            f'bestvideo{h}/'
            f'best{h}/best')


def policy_info(url):
    """CloudFront signed-URL check. Returns ('expired'|'warn'|'', message)."""
    if 'Policy=' not in url:
        return '', ''
    try:
        qs = parse_qs(urlparse(url).query)
        pol = qs.get('Policy', [None])[0]
        if not pol:
            return '', ''
        pol += '=' * (-len(pol) % 4)
        data = json.loads(base64.urlsafe_b64decode(pol).decode('utf-8', 'ignore'))
        epoch = int(data['Statement'][0]['Condition']['AWS:EpochTime'])
        exp = time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(epoch))
        if epoch < time.time():
            return 'expired', f'Signed link expired at {exp}. Re-export a fresh link.'
        if epoch - time.time() < 1800:
            return 'warn', f'Link expires {exp}'
    except Exception:
        return '', ''
    return '', ''


M3U8_RE = re.compile(r'https?://[^\s"\'<>\\]+?\.m3u8(?:\?[^\s"\'<>]*)?', re.I)


def extract_m3u8(html):
    """Signed .m3u8 URLs from a saved page export; master playlists first."""
    urls = []
    for u in M3U8_RE.findall(html):
        u = u.replace('\\u0026', '&').replace('\\&', '&').replace('&amp;', '&')
        u = u.rstrip('.,;')
        if u not in urls:
            urls.append(u)
    urls.sort(key=lambda u: (0 if 'master' in u else 1, len(u)))
    return urls


def _progress_hook(job_id):
    def hook(d):
        st = d.get('status')
        if st == 'downloading':
            entry = {'stage': 'download'}
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            done = d.get('downloaded_bytes') or 0
            if total:
                entry['pct'] = round(done * 100 / total, 1)
            if d.get('speed'):
                entry['speed'] = (f"{d['speed'] / 1048576:.1f} MB/s"
                                  if d['speed'] >= 1048576
                                  else f"{d['speed'] / 1024:.0f} KB/s")
            if d.get('eta') is not None:
                entry['eta'] = d['eta']
            PROGRESS[job_id] = entry
        elif st in ('finished', 'processing'):
            PROGRESS[job_id] = {'stage': 'processing'}
    return hook


def do_download(url, fmt, quality, pack, job_id):
    """Run the full pipeline; returns a Flask response or raises ValueError."""
    warnings = []
    state, msg = policy_info(url)
    if state == 'expired':
        raise ValueError(msg)
    if state == 'warn':
        warnings.append(msg)

    workdir = _fresh_workdir()

    if fmt == 'mp3':
        ydl_opts = {
            'outtmpl': os.path.join(workdir, '%(title)s.%(ext)s'),
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'quiet': True,
            'no_warnings': True,
        }
    else:
        ydl_opts = {
            'outtmpl': os.path.join(workdir, '%(title)s.%(ext)s'),
            'format': video_format(None if quality == 'auto' else int(quality)),
            'quiet': True,
            'no_warnings': True,
            'merge_output_format': 'mp4',
        }
    if job_id:
        ydl_opts['progress_hooks'] = [_progress_hook(job_id)]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        downloaded = find_downloaded_file(ydl, info)

    if not downloaded:
        raise RuntimeError('Download failed')

    title = info.get('title', 'video')

    if fmt == 'mp3':
        resp = send_file(
            convert_to_mp3(downloaded, title),
            as_attachment=True,
            download_name=f'{title}.mp3',
            mimetype='audio/mpeg'
        )
        if warnings:
            resp.headers['X-Warning'] = ' · '.join(warnings)
        return resp

    vcodec, acodec = probe_streams(downloaded)
    if acodec is None:
        warnings.append('source has no audio track')
    if vcodec is not None and vcodec != 'h264':
        final_file = reencode_to_h264(downloaded)
    else:
        final_file = downloaded

    if pack:
        zip_file = build_pack(final_file, title)
        resp = send_file(
            zip_file,
            as_attachment=True,
            download_name=f'{title}_pack.zip',
            mimetype='application/zip'
        )
        if warnings:
            resp.headers['X-Warning'] = ' · '.join(warnings)
        return resp

    resp = send_file(
        final_file,
        as_attachment=True,
        download_name=f'{title}.mp4',
        mimetype='video/mp4'
    )
    if warnings:
        resp.headers['X-Warning'] = ' · '.join(warnings)
    return resp


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/progress/<job_id>')
def progress(job_id):
    return jsonify(PROGRESS.get(job_id, {}))


@app.route('/upload', methods=['POST'])
def upload_page():
    """Extract signed .m3u8 URL(s) from a saved page export (Loom flow)."""
    f = request.files.get('page')
    if not f:
        return jsonify({'error': 'No file provided'}), 400
    html = f.read().decode('utf-8', 'ignore')
    urls = extract_m3u8(html)
    if not urls:
        return jsonify({'error': 'No video URLs found in that file. '
                        'Re-export the page after the video starts playing.'}), 400
    return jsonify({'url': urls[0], 'found': len(urls)})


@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    url = data.get('url', '').strip()
    fmt = (data.get('format') or 'mp4').strip().lower()
    quality = str(data.get('quality') or 'auto').strip().lower()
    pack = bool(data.get('pack'))
    job_id = (data.get('job_id') or '').strip()

    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    if fmt not in ('mp4', 'mp3'):
        return jsonify({'error': 'Unsupported format'}), 400
    if quality not in ('auto', '1080', '720', '480'):
        return jsonify({'error': 'Unsupported quality'}), 400

    print(f'[download-start] format={fmt} quality={quality} pack={pack} url={url}',
          flush=True)
    try:
        return do_download(url, fmt, quality, pack, job_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    # use_reloader=False: the debug reloader restarts mid-request when
    # stdlib modules (e.g. _strptime) are imported lazily during extraction,
    # killing the connection ("Failed to fetch"). threaded=True so a long
    # download doesn't block other requests.
    app.run(debug=True, use_reloader=False, threaded=True)
