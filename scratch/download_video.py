import yt_dlp
import os

downloads = os.path.join(os.environ.get('USERPROFILE',''), 'Downloads')
url = 'https://youtu.be/BThCK0HF1Dw?list=RDBThCK0HF1DW'

ydl_opts = {
    'outtmpl': os.path.join(downloads, '%(title)s.%(ext)s'),
    'quiet': True,
    'no_warnings': True,
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    try:
        info = ydl.extract_info(url, download=True)
        print(f"Downloaded: {info.get('title', 'unknown')}")
    except Exception as e:
        print(f"Error: {e}")