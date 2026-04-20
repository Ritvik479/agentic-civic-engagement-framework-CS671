import os
import subprocess

# ---- CONFIG ----

BASE_DIR = "data/test_vision/videos"
RAW_DIR = os.path.join(BASE_DIR, "raw")

# Absolute path to FFmpeg executable.
# Required for video trimming since FFmpeg is not added to system PATH.
# Update this path if FFmpeg location changes.
FFMPEG_PATH = r"C:\Users\gargr\Downloads\ffmpeg-8.1-essentials_build\ffmpeg-8.1-essentials_build\bin\ffmpeg.exe"

VIDEOS = [
    {
        "name": "pollution_smoke",
        "url": "https://www.youtube.com/watch?v=OK7DG5H-M08",
        "start": "00:01:51",
        "end": "00:02:36"
    },
    {
        "name": "garbage_dump",
        "url": "https://www.youtube.com/watch?v=0zjsHF-QB5Y",
        "start": "00:00:32",
        "end": "00:00:57"
    },
    {
        "name": "road_pothole",
        "url": "https://www.youtube.com/watch?v=q_YVd4X3w4M",
        "start": "00:00:02",
        "end": "00:00:27"
    },
    {
        "name": "drain_overflow",
        "url": "https://www.youtube.com/shorts/KR8BTmyfC1U",
        "start": "00:00:00",
        "end": "00:00:06"
    },
    {
        "name": "stray_animals",
        "url": "https://www.youtube.com/watch?v=0N1xSMBNEko",
        "start": "00:00:01",
        "end": "00:00:14"
    },
    {
        "name": "hindi_audio",
        "url": "https://www.youtube.com/watch?v=9n8sXo2l7jE",
        "start": "00:00:00",
        "end": "00:00:50"
    },
    {
        "name": "no_audio",
        "url": "https://pixabay.com/videos/pollution-smoke-factory-industry-62341/",
        "start": None,
        "end": None
    },
    {
        "name": "embedded_subs",
        "url": "https://www.youtube.com/watch?v=puSg1CMWByY",
        "start": None,
        "end": None
    }
]


def ensure_dirs():
    os.makedirs(BASE_DIR, exist_ok=True)
    os.makedirs(RAW_DIR, exist_ok=True)


def download_video(name, url):
    print(f"\n⬇️ Downloading: {name}")

    output_path = os.path.join(RAW_DIR, f"{name}.%(ext)s")

    command = [
        "yt-dlp",
        "-f", "mp4",
        "-o", output_path,
        url
    ]

    subprocess.run(command)


def trim_video(name, start, end):
    if start is None or end is None:
        print(f"⏭ Skipping trim for {name}")
        return

    input_path = os.path.join(RAW_DIR, f"{name}.mp4")
    output_path = os.path.join(BASE_DIR, f"{name}.mp4")

    print(f"✂️ Trimming {name}: {start} → {end}")

    command = [
        FFMPEG_PATH,
        "-y",
        "-ss", start,
        "-to", end,
        "-i", input_path,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        output_path
    ]

    subprocess.run(command)


def move_full_video(name):
    input_path = os.path.join(RAW_DIR, f"{name}.mp4")
    output_path = os.path.join(BASE_DIR, f"{name}.mp4")

    if os.path.exists(input_path):
        os.rename(input_path, output_path)


def main():
    ensure_dirs()

    for vid in VIDEOS:
        download_video(vid["name"], vid["url"])

    for vid in VIDEOS:
        if vid["start"]:
            trim_video(vid["name"], vid["start"], vid["end"])
        else:
            move_full_video(vid["name"])

    print("\n✅ All videos ready!")


if __name__ == "__main__":
    main()