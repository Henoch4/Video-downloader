import os
import re
import subprocess
import yt_dlp
from flask import Flask, render_template, request, send_file, jsonify
import tempfile

app = Flask(__name__, template_folder='templates')

DOWNLOADS_FOLDER = os.path.join(os.environ.get('USERPROFILE', ''), 'Downloads')
TEMP_DIR = os.path.join(os.environ.get('USERPROFILE', ''), 'AppData', 'Local', 'Temp', 'video_converter')
os.makedirs(TEMP_DIR, exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

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


def video_codec(path):
    """Return the video codec name (e.g. h264, vp9) or None for audio-only."""
    p = subprocess.run(['ffmpeg', '-i', path],
                       capture_output=True, text=True, errors='replace')
    m = re.search(r'Video:\s*([a-z0-9_]+)', p.stderr)
    return m.group(1) if m else None


def reencode_to_h264(src):
    """Re-encode to H.264/AAC MP4 so it plays everywhere. Returns new path."""
    base = os.path.splitext(src)[0]
    dst = base + '.h264.mp4'
    subprocess.run([
        'ffmpeg', '-y', '-i', src,
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
        'ffmpeg', '-y', '-i', src, '-vn',
        '-c:a', 'libmp3lame', '-q:a', '0',
        '-id3v2_version', '3',
        '-metadata', f'title={title}',
        dst
    ], check=True, capture_output=True)
    os.remove(src)
    return dst


@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    url = data.get('url', '').strip()
    fmt = (data.get('format') or 'mp4').strip().lower()
    
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    if fmt not in ('mp4', 'mp3'):
        return jsonify({'error': 'Unsupported format'}), 400
    
    print(f'[download-start] format={fmt} url={url}', flush=True)
    try:
        # Clean up any previous files (skip locked/stale ones)
        for f in os.listdir(TEMP_DIR):
            try:
                os.remove(os.path.join(TEMP_DIR, f))
            except OSError:
                pass
        
        if fmt == 'mp3':
            ydl_opts = {
                'outtmpl': os.path.join(TEMP_DIR, '%(title)s.%(ext)s'),
                'format': 'bestaudio[ext=m4a]/bestaudio/best',
                'quiet': True,
                'no_warnings': True,
            }
        else:
            # Prefer H.264/MP4 (avc1) sources so no re-encode is needed
            ydl_opts = {
                'outtmpl': os.path.join(TEMP_DIR, '%(title)s.%(ext)s'),
                'format': ('bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/'
                           'bestvideo[ext=mp4]+bestaudio/'
                           'bestvideo[ext=mp4]/'
                           'bestvideo+bestaudio/best'),
                'quiet': True,
                'no_warnings': True,
                'merge_output_format': 'mp4',
            }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded = find_downloaded_file(ydl, info)
        
        if not downloaded:
            return jsonify({'error': 'Download failed'}), 500
        
        title = info.get('title', 'video')
        
        if fmt == 'mp3':
            final_file = convert_to_mp3(downloaded, title)
            return send_file(
                final_file,
                as_attachment=True,
                download_name=f'{title}.mp3',
                mimetype='audio/mpeg'
            )
        
        # Guarantee a playable H.264 MP4: re-encode if codec isn't h264
        codec = video_codec(downloaded)
        if codec is not None and codec != 'h264':
            final_file = reencode_to_h264(downloaded)
        else:
            final_file = downloaded
        
        return send_file(
            final_file,
            as_attachment=True,
            download_name=f'{title}.mp4',
            mimetype='video/mp4'
        )
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # use_reloader=False: the debug reloader restarts mid-request when
    # stdlib modules (e.g. _strptime) are imported lazily during extraction,
    # killing the connection ("Failed to fetch"). threaded=True so a long
    # download doesn't block other requests.
    app.run(debug=True, use_reloader=False, threaded=True)