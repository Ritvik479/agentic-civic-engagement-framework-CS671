"""
context_extractor_tool.py
═════════════════════════
Agent 0 — Multimodal Context Extractor.
Acquires the video, extracts the best frame, transcript, and on-screen text.
Passes a clean context object to Agent 1 and Agent 2.

Does NOT run issue detection or location resolution — those belong to
Agent 1 and Agent 2 respectively, orchestrated by vision_pipeline_tool.py.

Output context dict:
    {
        "video_path":       str,
        "frame_path":       str,
        "frame_b64":        str,   # base64 JPEG of best frame
        "transcript":       str,   # raw transcript (original language)
        "transcript_en":    str,   # English translation
        "transcript_lang":  str,   # detected language code
        "transcript_source":str,   # "embedded_subtitle" | "youtube_auto_sub" | "whisper" | "none"
        "on_screen_text":   str,   # text visible in frame (signs, overlays, etc.)
        "social_caption":   str,
        "social_tags":      list,
        "social_title":     str,
        "whatsapp_text":    str,
        "user_location":    str,
        "source_url":       str,
        "error":            str,   # set only on failure
    }
"""

import os
import re
import uuid
import json
import base64
import subprocess

import cv2
import whisper
import yt_dlp
from groq import Groq

# ── Groq client ───────────────────────────────────────────────────────────────
client = Groq()  # reads GROQ_API_KEY from environment

# ── Whisper model — loaded once at import time, not on every call ─────────────
# "medium" handles Hindi / regional languages well; swap to "large-v3" for
# better accuracy at the cost of speed.
_WHISPER_MODEL = whisper.load_model("medium")

# ── YOLO model (used only for frame scoring here, NOT issue detection) ────────
from ultralytics import YOLO
_YOLO_MODEL = YOLO("yolov8n.pt")   # lightweight nano — only used for scoring

# Objects that indicate a news-studio / indoor shot — penalise these frames
_INDOOR_STUDIO_LABELS = {
    'laptop', 'tv', 'monitor', 'keyboard', 'mouse',
    'remote', 'cell phone', 'book', 'clock',
    'tie', 'wine glass', 'fork', 'knife', 'spoon',
}

# ── Groq Vision prompt — extracts on-screen text ─────────────────────────────
_ON_SCREEN_TEXT_PROMPT = """\
Extract ALL visible text in this image — captions, overlays, subtitles,
shop signs, hoardings, road boards, handwritten signs, watermarks.
Return raw text only, no explanation.
If no text is visible, return an empty string.
"""


# ═════════════════════════════════════════════════════════════════════════════
# Frame extraction helpers
# ═════════════════════════════════════════════════════════════════════════════

def _sharpness(frame) -> float:
    """Laplacian variance — higher means sharper frame."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def _score_frame(frame) -> float:
    """
    Single YOLO pass per frame — replaces the original three separate passes.
    Penalises frames dominated by a reporter or studio objects.
    Returns raw sharpness if the frame looks like an outdoor civic scene.
    """
    sharpness = _sharpness(frame)
    results    = _YOLO_MODEL(frame, verbose=False)[0]
    frame_area = frame.shape[0] * frame.shape[1]

    person_area  = 0.0
    is_studio    = False

    for box in results.boxes:
        label = results.names[int(box.cls)]
        if label == 'person':
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            person_area += (x2 - x1) * (y2 - y1)
        if label in _INDOOR_STUDIO_LABELS:
            is_studio = True

    person_ratio = person_area / frame_area if frame_area > 0 else 0.0

    if person_ratio > 0.05 or is_studio:
        return sharpness * 0.01   # heavy penalty for talking-head / studio frames

    return sharpness


def extract_best_frame(video_path: str) -> str:
    """
    Samples 9 frames across the video (10 %–90 %), scores each with a single
    YOLO pass, saves the highest-scoring frame to a UUID-named tmp file.

    Returns: path to saved JPEG.
    Raises:  FileNotFoundError, ValueError on bad input.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    if total_frames < 1:
        cap.release()
        raise ValueError("Video has no readable frames")

    sample_points = [i / 10 for i in range(1, 10)]   # 0.1 … 0.9
    best_frame, best_score = None, -1.0

    for pct in sample_points:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total_frames * pct))
        ret, frame = cap.read()
        if not ret:
            continue
        score = _score_frame(frame)
        print(f"  [frame scorer] {int(pct*100):2d}%: score={score:.1f}")
        if score > best_score:
            best_score, best_frame = score, frame.copy()

    cap.release()

    if best_frame is None:
        raise ValueError("Could not extract any frame from video")

    out_path = f"/tmp/{uuid.uuid4()}.jpg"   # UUID — safe for concurrent users
    cv2.imwrite(out_path, best_frame)
    print(f"  [frame scorer] best frame → {out_path}  (score={best_score:.1f})")
    return out_path


# ═════════════════════════════════════════════════════════════════════════════
# Transcript helpers
# ═════════════════════════════════════════════════════════════════════════════

def _check_embedded_subtitles(video_path: str) -> bool:
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", video_path],
        capture_output=True, text=True
    )
    try:
        streams = json.loads(probe.stdout).get("streams", [])
        return any(s.get("codec_type") == "subtitle" for s in streams)
    except json.JSONDecodeError:
        return False


def _extract_embedded_subtitles(video_path: str) -> str:
    srt_path = f"/tmp/{uuid.uuid4()}.srt"   # UUID — safe for concurrent users
    subprocess.run(
        ["ffmpeg", "-i", video_path, "-map", "0:s:0", srt_path, "-y", "-loglevel", "error"],
        capture_output=True
    )
    if not os.path.exists(srt_path):
        return ""
    with open(srt_path, "r", encoding="utf-8", errors="ignore") as f:
        raw = f.read()
    os.remove(srt_path)
    # Strip SRT timestamps and index numbers
    lines = [
        line.strip() for line in raw.split("\n")
        if line.strip() and not line.strip().isdigit() and "-->" not in line
    ]
    return " ".join(lines)


def _extract_audio(video_path: str) -> str | None:
    """Extracts mono 16 kHz WAV for Whisper. Returns path or None if no audio."""
    audio_path = f"/tmp/{uuid.uuid4()}.wav"   # UUID — safe for concurrent users
    subprocess.run([
        "ffmpeg", "-i", video_path,
        "-ar", "16000", "-ac", "1", "-vn",
        audio_path, "-y", "-loglevel", "error"
    ], capture_output=True, text=True)

    if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
        print("  [transcript] No audio track found")
        return None
    return audio_path


def _get_transcript(video_path: str, youtube_auto_subs: str = '') -> dict:
    """
    Priority chain:
        1. Embedded subtitles (human-verified, most accurate)
        2. YouTube auto-generated subs (already downloaded by yt-dlp)
        3. Whisper transcription (local, multilingual)
        4. Empty fallback

    Returns: {text, language, source}
    """
    # Priority 1 — embedded subtitles
    if _check_embedded_subtitles(video_path):
        text = _extract_embedded_subtitles(video_path)
        if text:
            print(f"  [transcript] embedded subtitles ({len(text)} chars)")
            return {"text": text, "language": "unknown", "source": "embedded_subtitle"}

    # Priority 2 — YouTube auto-subs (passed in from yt-dlp extraction)
    if youtube_auto_subs:
        print(f"  [transcript] YouTube auto-subs ({len(youtube_auto_subs)} chars)")
        return {"text": youtube_auto_subs, "language": "unknown", "source": "youtube_auto_sub"}

    # Priority 3 — Whisper
    print("  [transcript] Running Whisper...")
    audio_path = _extract_audio(video_path)
    if audio_path is None:
        return {"text": "", "language": "unknown", "source": "none"}

    result = _WHISPER_MODEL.transcribe(audio_path, task="transcribe")
    os.remove(audio_path)
    print(f"  [transcript] Whisper done | lang={result['language']}")
    return {
        "text":     result["text"].strip(),
        "language": result["language"],
        "source":   "whisper",
    }


def _translate_to_english(text: str, source_language: str) -> str:
    """Translates to English via Groq. Returns text unchanged if already English."""
    if not text or source_language.lower() in ("en", "english"):
        return text

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": (
            "Translate the following text to English.\n"
            "Preserve tone exactly — urgency, anger, distress.\n"
            "Return ONLY the translated text, no explanation.\n\n"
            f"Text: {text}"
        )}],
        max_tokens=1000,
    )
    translated = response.choices[0].message.content.strip()
    print(f"  [translate] {source_language} → English")
    return translated


# ═════════════════════════════════════════════════════════════════════════════
# Social media download
# ═════════════════════════════════════════════════════════════════════════════

def _extract_from_social_url(url: str) -> dict:
    """
    Downloads video from YouTube or Instagram URL via yt-dlp.
    Also captures: caption, hashtags, auto-generated subtitles.

    Returns: {video_path, caption, tags, auto_subs, title}
    """
    # UUID in filename — safe for concurrent users
    output_template = f"/tmp/{uuid.uuid4()}_social.%(ext)s"

    ydl_opts = {
        "writesubtitles":    True,
        "writeautomaticsub": True,
        "subtitleslangs":    ["hi", "en", "pa", "ta", "te", "ml"],
        "outtmpl":           output_template,
        "format":            "mp4/best",
        "quiet":             True,
        "no_warnings":       True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info       = ydl.extract_info(url, download=True)
            video_path = ydl.prepare_filename(info)

            auto_subs = ""
            for ext in [".hi.vtt", ".en.vtt", ".hi.srt", ".en.srt"]:
                sub_file = re.sub(r"\.\w+$", ext, video_path)
                if os.path.exists(sub_file):
                    with open(sub_file, "r", encoding="utf-8") as f:
                        auto_subs = f.read()[:2000]
                    break

            print(f"  [social] Downloaded → {video_path}")
            return {
                "video_path": video_path,
                "caption":    info.get("description", ""),
                "tags":       info.get("tags", []),
                "auto_subs":  auto_subs,
                "title":      info.get("title", ""),
            }

    except Exception as e:
        print(f"  [social] Download failed: {e}")
        return {"video_path": None, "caption": "", "tags": [], "auto_subs": "", "title": ""}


# ═════════════════════════════════════════════════════════════════════════════
# On-screen text extraction (single Groq Vision call)
# ═════════════════════════════════════════════════════════════════════════════

def _extract_on_screen_text(frame_b64: str) -> str:
    """Single Groq Vision call — extracts all text visible in the frame."""
    try:
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{frame_b64}"}},
                {"type": "text", "text": _ON_SCREEN_TEXT_PROMPT},
            ]}],
            max_tokens=300,
        )
        text = response.choices[0].message.content.strip()
        print(f"  [on-screen text] {text[:80]}{'...' if len(text) > 80 else ''}")
        return text
    except Exception as e:
        print(f"  [on-screen text] failed: {e}")
        return ""


# ═════════════════════════════════════════════════════════════════════════════
# Agent 0 — public interface
# ═════════════════════════════════════════════════════════════════════════════

def extract_context(
    video_path:    str = None,
    url:           str = None,
    whatsapp_text: str = '',
    user_location: str = '',
) -> dict:
    """
    AGENT 0 — Multimodal Context Extractor.

    Builds the context object consumed by Agent 1 (issue detection)
    and Agent 2 (location resolution). Does NOT call either agent.

    Args:
        video_path:    path to an already-uploaded video file
        url:           YouTube or Instagram URL (used if video_path is absent)
        whatsapp_text: text forwarded alongside the video on WhatsApp
        user_location: location typed / pinned by the user on the phone UI

    Returns:
        context dict (see module docstring for full schema)
    """
    print("=" * 55)
    print("AGENT 0 — Context extraction starting...")
    print("=" * 55)

    context = {
        "video_path":        "",
        "frame_path":        "",
        "frame_b64":         "",
        "transcript":        "",
        "transcript_en":     "",
        "transcript_lang":   "unknown",
        "transcript_source": "none",
        "on_screen_text":    "",
        "social_caption":    "",
        "social_tags":       [],
        "social_title":      "",
        "whatsapp_text":     whatsapp_text,
        "user_location":     user_location,
        "source_url":        url or "",
        "error":             "",
    }

    # ── Step 1: Acquire video ────────────────────────────────────────────────
    youtube_auto_subs = ""

    if url:
        print("\n[1/4] Downloading from social media URL...")
        social = _extract_from_social_url(url)
        if social["video_path"] and os.path.exists(social["video_path"]):
            video_path = social["video_path"]
        context["social_caption"] = social["caption"]
        context["social_tags"]    = social["tags"]
        context["social_title"]   = social["title"]
        youtube_auto_subs         = social["auto_subs"]
    else:
        print("\n[1/4] Using uploaded video file...")

    if not video_path or not os.path.exists(video_path):
        print("  No valid video — cannot continue")
        context["error"] = "no_video"
        return context

    context["video_path"] = video_path

    # ── Step 2: Extract best frame ───────────────────────────────────────────
    print("\n[2/4] Extracting best frame...")
    try:
        frame_path = extract_best_frame(video_path)
        with open(frame_path, "rb") as fh:
            frame_b64 = base64.b64encode(fh.read()).decode("utf-8")
        context["frame_path"] = frame_path
        context["frame_b64"]  = frame_b64
    except Exception as e:
        print(f"  Frame extraction failed: {e}")
        frame_b64 = ""

    # ── Step 3: Transcript ───────────────────────────────────────────────────
    print("\n[3/4] Getting transcript...")
    t = _get_transcript(video_path, youtube_auto_subs)
    context["transcript"]        = t["text"]
    context["transcript_lang"]   = t["language"]
    context["transcript_source"] = t["source"]
    context["transcript_en"]     = _translate_to_english(t["text"], t["language"])

    # ── Step 4: On-screen text (one Groq Vision call) ────────────────────────
    if frame_b64:
        print("\n[4/4] Extracting on-screen text...")
        context["on_screen_text"] = _extract_on_screen_text(frame_b64)

    print("\n" + "=" * 55)
    print("AGENT 0 COMPLETE")
    print(f"  transcript   : {len(context['transcript'])} chars "
          f"(lang={context['transcript_lang']}, src={context['transcript_source']})")
    print(f"  on_screen    : {len(context['on_screen_text'])} chars")
    print(f"  frame        : {'✓' if context['frame_b64'] else '✗'}")
    print("=" * 55)

    return context