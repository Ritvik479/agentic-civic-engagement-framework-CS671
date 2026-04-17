"""
issue_detector_tool.py
══════════════════════
Agent 1 — Issue Detector.
Combines YOLO + Groq Vision (frame-based) with transcript and on-screen
text signals to produce a single canonical issue type.

Input:  context dict from context_extractor_tool.extract_context()
Output: {"issue_type": str, "confidence": float, "reasoning": str}

The output key is `issue_type` (not `label`) to match orchestrator.py directly.
"""

import os
import uuid
import json
import base64

from groq import Groq
from ultralytics import YOLO

# ── Groq client ───────────────────────────────────────────────────────────────
client = Groq()  # reads GROQ_API_KEY from environment

# ── YOLO model — loaded once at import time ───────────────────────────────────
_YOLO_MODEL = YOLO("yolov8n.pt")

# ── YOLO COCO class → raw issue type ─────────────────────────────────────────
_ISSUE_MAP = {
    'bottle': 'garbage', 'cup': 'garbage', 'handbag': 'garbage',
    'backpack': 'garbage', 'suitcase': 'garbage', 'dining table': 'garbage',
    'bowl': 'garbage', 'banana': 'garbage', 'apple': 'garbage',
    'sandwich': 'garbage', 'orange': 'garbage', 'broccoli': 'garbage',
    'carrot': 'garbage', 'hot dog': 'garbage', 'pizza': 'garbage',
    'donut': 'garbage', 'cake': 'garbage', 'chair': 'garbage',
    'couch': 'garbage', 'potted plant': 'garbage', 'bed': 'garbage',
    'vase': 'garbage', 'scissors': 'garbage', 'toothbrush': 'garbage',
    'teddy bear': 'garbage',
    'toilet': 'sanitation', 'sink': 'sanitation',
    'car': 'road_blockage', 'truck': 'road_blockage',
    'motorcycle': 'road_blockage', 'bus': 'road_blockage',
    'bicycle': 'road_blockage', 'train': 'road_blockage',
    'cow': 'stray_animal', 'dog': 'stray_animal', 'cat': 'stray_animal',
    'horse': 'stray_animal', 'elephant': 'stray_animal',
    'bear': 'stray_animal', 'zebra': 'stray_animal',
    'giraffe': 'stray_animal', 'sheep': 'stray_animal',
    'bench': 'infrastructure', 'fire hydrant': 'infrastructure',
    'stop sign': 'infrastructure',
}

# ── Raw label → canonical name expected by orchestrator / authority_data.json ─
_ISSUE_CANONICAL_MAP = {
    'garbage':        'Waste Management',
    'pollution':      'Air Pollution',
    'drain':          'Water Pollution',
    'road_blockage':  'Road Damage',
    'stray_animal':   'Animal Control',
    'sanitation':     'Public Sanitation',
    'infrastructure': 'Infrastructure Damage',
}

# ── Groq Vision fallback prompt ───────────────────────────────────────────────
_GROQ_VISION_ISSUE_PROMPT = """\
Look at this image carefully.
This is from a civic complaint video about environmental or infrastructure issues in India.
Identify what civic problem is shown. Choose exactly one category from this list:
- garbage (waste pile, litter, dump yard, trash, dirty area)
- pollution (dirty river, smoke, chemical waste, water pollution)
- drain (blocked drain, sewage overflow, waterlogging on road)
- road_blockage (broken road, pothole, encroachment, blocked path)
- stray_animal (stray dogs or cows on road or in public space)
- sanitation (open defecation area, dirty public toilet)
- infrastructure (broken streetlight, damaged public property, broken road sign)
- unknown (cannot determine any civic issue)
Return ONLY valid JSON — no extra text, no markdown, no explanation:
{"label": "garbage", "confidence": 0.85, "reasoning": "visible waste pile near road"}"""

# ── Multimodal refinement prompt ──────────────────────────────────────────────
_MULTIMODAL_ISSUE_PROMPT = """\
You are classifying a civic complaint video from India.
Use all available signals to identify the primary civic issue.

Visual detection: {visual}
Speech transcript (English): {transcript}
On-screen text: {on_screen}
WhatsApp context: {whatsapp}

Choose exactly one from:
garbage / pollution / drain / road_blockage / stray_animal / sanitation / infrastructure / unknown

Return JSON only — no markdown, no explanation:
{{"label": "...", "confidence": 0.0-1.0, "reasoning": "brief explanation"}}"""


# ═════════════════════════════════════════════════════════════════════════════
# Step A — YOLO detection
# ═════════════════════════════════════════════════════════════════════════════

def _yolo_detect(frame_path: str) -> dict:
    """
    Runs YOLO on the frame. Returns best civic issue match by confidence.
    Falls back to {'label': 'unknown', 'confidence': 0.0, 'reasoning': ''}
    if no mapped civic object is found.
    """
    results    = _YOLO_MODEL(frame_path, verbose=False)[0]
    detections = []
    obj_labels = []

    for box in results.boxes:
        obj_label = results.names[int(box.cls)]
        conf      = float(box.conf)
        issue     = _ISSUE_MAP.get(obj_label)
        print(f"    [YOLO] {obj_label:20s} conf={conf:.2f} → {issue or 'not in map'}")
        if issue:
            detections.append({'label': issue, 'confidence': round(conf, 3)})
            obj_labels.append(obj_label)

    if detections:
        best = max(detections, key=lambda x: x['confidence'])
        best['reasoning'] = f"Detected {', '.join(obj_labels)} in civic area"
        print(f"  [YOLO] result → {best}")
        return best

    print("  [YOLO] no civic object found")
    return {'label': 'unknown', 'confidence': 0.0, 'reasoning': ''}


# ═════════════════════════════════════════════════════════════════════════════
# Step B — Groq Vision fallback
# ═════════════════════════════════════════════════════════════════════════════

def _groq_vision_detect(frame_b64: str) -> dict:
    """
    Groq Vision fallback — used only when YOLO finds no civic object.
    Sends base64 frame to Llama 4 Scout for visual classification.
    """
    try:
        response = client.chat.completions.create(
            model='meta-llama/llama-4-scout-17b-16e-instruct',
            messages=[{'role': 'user', 'content': [
                {'type': 'image_url',
                 'image_url': {'url': f'data:image/jpeg;base64,{frame_b64}'}},
                {'type': 'text', 'text': _GROQ_VISION_ISSUE_PROMPT},
            ]}],
            max_tokens=150,
        )
        raw    = response.choices[0].message.content.strip()
        raw    = raw.replace('```json', '').replace('```', '').strip()
        result = json.loads(raw)
        print(f"  [Groq Vision] {result}")
        return {
            'label':      result.get('label', 'unknown'),
            'confidence': float(result.get('confidence', 0.0)),
            'reasoning':  result.get('reasoning', ''),
        }
    except json.JSONDecodeError as e:
        print(f"  [Groq Vision] JSON parse error: {e}")
        return {'label': 'unknown', 'confidence': 0.0, 'reasoning': ''}
    except Exception as e:
        print(f"  [Groq Vision] error: {e}")
        return {'label': 'unknown', 'confidence': 0.0, 'reasoning': ''}


# ═════════════════════════════════════════════════════════════════════════════
# Step C — Multimodal refinement
# ═════════════════════════════════════════════════════════════════════════════

def _multimodal_refine(
    vision_result: dict,
    transcript:    str,
    on_screen:     str,
    whatsapp:      str,
) -> dict:
    """
    Asks Groq text LLM to verify/refine the visual classification using
    transcript, on-screen text, and WhatsApp context as additional signals.
    Falls back to vision_result unchanged if the API call fails.
    """
    try:
        response = client.chat.completions.create(
            model='llama-3.3-70b-versatile',
            messages=[{'role': 'user', 'content': _MULTIMODAL_ISSUE_PROMPT.format(
                visual     = (f"{vision_result['label']} "
                              f"({vision_result['confidence']:.2f}) — "
                              f"{vision_result.get('reasoning', '')}"),
                transcript = transcript[:400] if transcript else 'none',
                on_screen  = on_screen[:200]  if on_screen  else 'none',
                whatsapp   = whatsapp[:200]   if whatsapp   else 'none',
            )}],
            max_tokens=150,
        )
        raw     = response.choices[0].message.content.strip()
        raw     = raw.replace('```json', '').replace('```', '').strip()
        refined = json.loads(raw)
        print(f"  [multimodal refine] {refined}")
        return refined
    except Exception as e:
        print(f"  [multimodal refine] failed: {e} — using vision result")
        return vision_result


# ═════════════════════════════════════════════════════════════════════════════
# Agent 1 — public interface
# ═════════════════════════════════════════════════════════════════════════════

def detect_issue(context: dict) -> dict:
    """
    AGENT 1 — Issue Detector.

    Three-step pipeline:
        A. YOLO on best frame (fast, offline)
        B. Groq Vision fallback if YOLO finds nothing
        C. Multimodal refinement using transcript + on-screen + WhatsApp

    Args:
        context: dict produced by context_extractor_tool.extract_context()

    Returns:
        {
            "issue_type":  str,    # canonical e.g. "Waste Management"
            "confidence":  float,
            "reasoning":   str,
        }
    """
    print("\n" + "=" * 55)
    print("AGENT 1 — Issue detection starting...")
    print("=" * 55)

    frame_path = context.get('frame_path', '')
    frame_b64  = context.get('frame_b64', '')
    transcript = context.get('transcript_en', '')
    on_screen  = context.get('on_screen_text', '')
    whatsapp   = context.get('whatsapp_text', '')

    # ── Step A: YOLO ─────────────────────────────────────────────────────────
    vision_result = {'label': 'unknown', 'confidence': 0.0, 'reasoning': ''}

    if frame_path and os.path.exists(frame_path):
        print("\n[A] Running YOLO...")
        vision_result = _yolo_detect(frame_path)
    elif frame_b64:
        # frame_path unavailable — decode to tmp file for YOLO
        tmp_path = f"/tmp/{uuid.uuid4()}.jpg"
        with open(tmp_path, 'wb') as fh:
            fh.write(base64.b64decode(frame_b64))
        print("\n[A] Running YOLO (from b64)...")
        vision_result = _yolo_detect(tmp_path)
        os.remove(tmp_path)
    else:
        print("\n[A] No frame available — skipping YOLO")

    # ── Step B: Groq Vision fallback ─────────────────────────────────────────
    if vision_result['label'] == 'unknown' and frame_b64:
        print("\n[B] YOLO found nothing — running Groq Vision fallback...")
        vision_result = _groq_vision_detect(frame_b64)

    # ── Step C: Multimodal refinement ─────────────────────────────────────────
    print("\n[C] Multimodal refinement...")
    refined = _multimodal_refine(vision_result, transcript, on_screen, whatsapp)

    # ── Canonicalise → orchestrator-compatible issue_type ────────────────────
    raw_label  = refined.get('label', 'unknown')
    issue_type = _ISSUE_CANONICAL_MAP.get(raw_label, 'Waste Management')

    print(f"\n  {raw_label} → canonical: \"{issue_type}\"  "
          f"conf={refined.get('confidence', 0.0):.2f}")
    print("=" * 55)

    return {
        'issue_type': issue_type,
        'confidence': float(refined.get('confidence', 0.0)),
        'reasoning':  refined.get('reasoning', ''),
    }