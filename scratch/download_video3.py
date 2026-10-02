import yt_dlp
import os

downloads = os.path.join(os.environ.get('USERPROFILE',''), 'Downloads')
url = 'https://youtu.be/BThCK0HF1Dw?si=wGdwe8Ot0l8k-EQz'

ydl_opts = {
    'outtmpl': os.path.join(downloads, '%(title)s.%(ext)s'),
    'quiet': True,
    'no_warnings': True,
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    try:
        info = ydl.extract_info(url, download=True)
        print(f"Downloaded: {info.get('title', 'unknown')}")
        print(f"File: {ydl.prepare_filename(info)}")
    except Exception as e:
        print(f"Error: {e}")