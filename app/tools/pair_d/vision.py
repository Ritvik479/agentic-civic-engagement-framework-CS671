# app/tools/pair_d/vision.py
# Person 8 — frame extraction + issue detection
# delivers: extract_best_frame() + detect_issue()
# fixes:
#   - smart frame selection (avoids news anchor / talking head frames)
#   - Groq Vision fallback when YOLO returns unknown
#   - expanded ISSUE_MAP

import cv2
import os
import base64
import json
from ultralytics import YOLO
from smolagents import tool
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# load model once at module level — never inside a function
model = YOLO('yolov8n.pt')
client = Groq()

# YOLO object label → civic issue type
# covers what YOLO's 80 COCO classes look like in civic violation videos
ISSUE_MAP = {
    # garbage / litter
    'bottle':        'garbage',
    'cup':           'garbage',
    'handbag':       'garbage',
    'backpack':      'garbage',
    'suitcase':      'garbage',
    'dining table':  'garbage',
    'bowl':          'garbage',
    'banana':        'garbage',
    'apple':         'garbage',
    'sandwich':      'garbage',
    'orange':        'garbage',
    'broccoli':      'garbage',
    'carrot':        'garbage',
    'hot dog':       'garbage',
    'pizza':         'garbage',
    'donut':         'garbage',
    'cake':          'garbage',
    'chair':         'garbage',
    'couch':         'garbage',
    'potted plant':  'garbage',
    'bed':           'garbage',
    'vase':          'garbage',
    'scissors':      'garbage',
    'toothbrush':    'garbage',
    'teddy bear':    'garbage',
    # sanitation
    'toilet':        'sanitation',
    'sink':          'sanitation',
    # road / traffic
    'car':           'road_blockage',
    'truck':         'road_blockage',
    'motorcycle':    'road_blockage',
    'bus':           'road_blockage',
    'bicycle':       'road_blockage',
    'train':         'road_blockage',
    # stray animals
    'cow':           'stray_animal',
    'dog':           'stray_animal',
    'cat':           'stray_animal',
    'horse':         'stray_animal',
    'elephant':      'stray_animal',
    'bear':          'stray_animal',
    'zebra':         'stray_animal',
    'giraffe':       'stray_animal',
    'sheep':         'stray_animal',
    # infrastructure
    'bench':         'infrastructure',
    'fire hydrant':  'infrastructure',
    'stop sign':     'infrastructure',
}

# objects that suggest a news/studio/indoor shot — avoid these frames
INDOOR_STUDIO_LABELS = {
    'laptop', 'tv', 'monitor', 'keyboard', 'mouse',
    'remote', 'cell phone', 'book', 'clock', 'scissors',
    'tie', 'wine glass', 'fork', 'knife', 'spoon',
}

GROQ_VISION_PROMPT = """Look at this image carefully.
This is from a civic complaint video about environmental or infrastructure issues in India.
Identify what civic problem is shown. Choose exactly one category from this list:
- garbage     (waste pile, litter, dump yard, trash, dirty area)
- pollution   (dirty river, smoke, chemical waste, water pollution)
- drain       (blocked drain, sewage overflow, waterlogging on road)
- road_blockage (broken road, pothole, encroachment, blocked path)
- stray_animal (stray dogs or cows on road or in public space)
- sanitation  (open defecation area, dirty public toilet)
- infrastructure (broken streetlight, damaged public property, broken road sign)
- unknown     (cannot determine any civic issue)

Return ONLY valid JSON — no extra text, no markdown, no explanation:
{"label": "garbage", "confidence": 0.85, "reasoning": "visible waste pile near road"}"""


# ─── helpers ────────────────────────────────────────────────────────────────

def _sharpness(frame):
    """Score frame sharpness using Laplacian variance. Higher = clearer."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def _person_ratio(frame) -> float:
    """
    Estimate how much of the frame is a close-up person.
    Uses YOLO person detections instead of haar cascade.
    Returns float 0.0 to 1.0
    """
    results = model(frame, verbose=False)[0]
    frame_area = frame.shape[0] * frame.shape[1]
    person_area = 0
    for box in results.boxes:
        label = results.names[int(box.cls)]
        if label == 'person':
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            person_area += (x2 - x1) * (y2 - y1)
    return person_area / frame_area if frame_area > 0 else 0.0
    


def _is_studio_frame(frame) -> bool:
    """
    Quick YOLO check — if frame has studio/indoor objects, skip it.
    Returns True if frame looks like a news studio / interview.
    """
    results = model(frame, verbose=False)[0]
    for box in results.boxes:
        label = results.names[int(box.cls)]
        if label in INDOOR_STUDIO_LABELS:
            return True
    return False


def _score_frame(frame) -> float:
    sharpness = _sharpness(frame)
    person_r = _person_ratio(frame)

    # raised from 0.10 to 0.05 — stricter person penalty
    if person_r > 0.05:
        return sharpness * 0.01  # almost zero score for person frames

    if _is_studio_frame(frame):
        return sharpness * 0.01

    return sharpness


def _groq_vision_classify(frame_path: str) -> dict:
    """
    Send frame to Groq Vision (llama-3.2-11b-vision-preview).
    Used as fallback when YOLO finds nothing in ISSUE_MAP.
    """
    with open(frame_path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode('utf-8')
    try:
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": GROQ_VISION_PROMPT
                    }
                ]
            }],
            max_tokens=150
        )
        raw = response.choices[0].message.content.strip()
        # strip markdown fences if Groq wraps in ```json
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)
        print(f"  [Groq Vision] {result}")
        return {
            "label": result.get("label", "unknown"),
            "confidence": float(result.get("confidence", 0.0))
        }
    except json.JSONDecodeError as e:
        print(f"  [Groq Vision] JSON parse error: {e} — raw: {raw}")
        return {"label": "unknown", "confidence": 0.0}
    except Exception as e:
        print(f"  [Groq Vision] error: {e}")
        return {"label": "unknown", "confidence": 0.0}


# ─── tools (delivered to SmolAgents / Pair B) ───────────────────────────────

@tool
def extract_best_frame(video_path: str) -> str:
    """
    Extract the best frame from a video file for civic issue detection.
    Samples frames across the video and scores each one.
    Avoids news anchor / studio / talking head frames.
    Picks the frame most likely to show the actual civic violation.

    Args:
        video_path: full path to the video file (.mp4 or any format)
    Returns:
        path to saved JPEG frame at /tmp/best_frame.jpg
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

    # sample more points across the video — 10 evenly spaced
    # more samples = better chance of hitting actual scene footage
    sample_points = [i / 10 for i in range(1, 10)]  # 10%, 20%, ... 90%

    best_frame, best_score = None, -1

    for pct in sample_points:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total_frames * pct))
        ret, frame = cap.read()
        if not ret:
            continue
        score = _score_frame(frame)
        print(f"  frame at {int(pct*100)}%: score={score:.1f}")
        if score > best_score:
            best_score, best_frame = score, frame.copy()

    cap.release()

    if best_frame is None:
        raise ValueError("Could not extract any frame from video")

    out_path = "/tmp/best_frame.jpg"
    cv2.imwrite(out_path, best_frame)
    print(f"  best frame saved: {out_path} (score={best_score:.1f})")
    return out_path


@tool
def detect_issue(frame_path: str) -> dict:
    """
    Detect civic issue type from a video frame.
    Step 1: YOLOv8 object detection — fast, works offline.
    Step 2: If YOLO finds nothing useful, Groq Vision classifies the scene.

    Args:
        frame_path: path to JPEG image file
    Returns:
        dict with keys:
            label (str)      — issue type e.g. 'garbage', 'pollution', 'drain'
            confidence (float) — 0.0 to 1.0
    """
    if not os.path.exists(frame_path):
        return {"label": "unknown", "confidence": 0.0}

    # step 1: YOLO object detection
    results = model(frame_path, verbose=False)[0]
    detections = []

    print(f"  [YOLO] all detections:")
    for box in results.boxes:
        label = results.names[int(box.cls)]
        conf  = float(box.conf)
        issue = ISSUE_MAP.get(label)
        print(f"    {label:20s} conf={conf:.2f}  →  {issue or 'not in map'}")
        if issue:
            detections.append({
                "label": issue,
                "confidence": round(conf, 3)
            })

    if detections:
        best = max(detections, key=lambda x: x["confidence"])
        print(f"  [YOLO] returning: {best}")
        return best

    # step 2: YOLO found nothing in ISSUE_MAP — use Groq Vision
    print("  [YOLO] no civic issue found — falling back to Groq Vision")
    return _groq_vision_classify(frame_path)