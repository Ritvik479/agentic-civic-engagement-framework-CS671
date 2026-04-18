"""
location_resolver_tool.py
═════════════════════════
Agent 2 — Location Resolver.
Combines three weighted signals to determine where the civic issue is located.

Signal weights:
    user input   → 0.85  (fixed — human confirmation, most trusted)
    transcript   → 0.60 × transcript_confidence  (speech is explicit)
    vision frame → 0.15 × vision_confidence      (indirect visual cues)

Input:  frame_b64, user_location, social_caption, transcript
        (all sourced from context dict produced by Agent 0)

Output:
    {
        "state":          str,
        "district":       str,
        "location_label": str,   # "District, State"
        "confidence":     float,
        "dominant_signal":str,   # "user" | "transcript" | "vision"
        "needs_user_input": bool,
    }
"""

import json

from groq import Groq
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
import re

# ── Groq client ───────────────────────────────────────────────────────────────
client     = Groq()  # reads GROQ_API_KEY from environment
geolocator = Nominatim(user_agent="civic_complaint_agent")

# ── Signal weights ────────────────────────────────────────────────────────────
_WEIGHT_USER       = 0.85
_WEIGHT_TRANSCRIPT = 0.60   # scaled by transcript_confidence
_WEIGHT_VISION     = 0.15   # scaled by vision_confidence
_MAX_WEIGHT        = _WEIGHT_USER  # used for confidence normalisation

# ── Groq Vision — location detection prompt ───────────────────────────────────
_VISION_LOCATION_PROMPT = """\
Analyse this image carefully. Look for:
- Any visible text: shop signs, road boards, hoardings, vehicle number plates, building names (Hindi or English)
- Geographical features: mountains, rivers, terrain, vegetation style
- Architectural style or urban / rural character
- Any other location clues specific to India

Return JSON only — no markdown, no explanation:
{"location": "city, district, state", "confidence": 0.0-1.0, "reasoning": "what clues you used"}
If you cannot determine location at all, return confidence: 0.0
"""

# ── Groq text — transcript location prompt ────────────────────────────────────
_TRANSCRIPT_LOCATION_PROMPT = """\
You are analysing a transcript from a civic complaint video recorded in India.
Extract the location where the civic issue is occurring.

Transcript:
{transcript}

Return JSON only — no markdown, no explanation:
{{"location": "city or district, state", "confidence": 0.0-1.0, "reasoning": "what clue you used"}}

Rules:
- Location must be where the ISSUE is, not where the reporter is based.
- If the same place is mentioned multiple times, confidence should be high (0.8+).
- If no location is mentioned at all, return {{"location": "", "confidence": 0.0, "reasoning": "not mentioned"}}.
"""


# ═════════════════════════════════════════════════════════════════════════════
# Signal extractors
# ═════════════════════════════════════════════════════════════════════════════

def _vision_location(frame_b64: str, social_caption: str = '') -> dict:
    """
    Groq Vision — extracts location clues from the best frame.
    Lowest-weight signal (0.15) — visual cues are indirect.
    """
    prompt = _VISION_LOCATION_PROMPT
    if social_caption:
        prompt += f"\n\nAdditional context from social media caption: {social_caption[:300]}"

    try:
        response = client.chat.completions.create(
            model='meta-llama/llama-4-scout-17b-16e-instruct',
            messages=[{'role': 'user', 'content': [
                {'type': 'image_url',
                 'image_url': {'url': f'data:image/jpeg;base64,{frame_b64}'}},
                {'type': 'text', 'text': prompt},
            ]}],
            max_tokens=200,
        )
        raw = response.choices[0].message.content.strip()
        # FIX
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not match:
            raise json.JSONDecodeError("No JSON object found", raw, 0)
        result = json.loads(match.group(0))
        print(f"  [vision location] {result.get('location', '')} "
              f"(conf={result.get('confidence', 0.0):.2f})")
        return result
    except json.JSONDecodeError:
        print("  [vision location] non-JSON response — confidence set to 0")
        return {'location': '', 'confidence': 0.0, 'reasoning': ''}
    except Exception as e:
        print(f"  [vision location] error: {e}")
        return {'location': '', 'confidence': 0.0, 'reasoning': str(e)}


def _transcript_location(transcript: str) -> dict:
    """
    Groq text LLM — extracts location from English transcript.
    Primary speech signal (0.60). Speech is explicit; always wins over vision.
    """
    if not transcript or not transcript.strip():
        return {'location': '', 'confidence': 0.0, 'reasoning': 'no transcript'}

    try:
        response = client.chat.completions.create(
            model='llama-3.3-70b-versatile',
            messages=[{'role': 'user', 'content':
                _TRANSCRIPT_LOCATION_PROMPT.format(transcript=transcript[:1500])
            }],
            max_tokens=150,
        )
        raw    = response.choices[0].message.content.strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not match:
            raise json.JSONDecodeError("No JSON object found", raw, 0)
        result = json.loads(match.group(0))
        print(f"  [transcript location] {result.get('location', '')} "
              f"(conf={result.get('confidence', 0.0):.2f})")
        return result
    except json.JSONDecodeError as e:
        print(f"  [transcript location] JSON parse error: {e}")
        return {'location': '', 'confidence': 0.0, 'reasoning': 'parse error'}
    except Exception as e:
        print(f"  [transcript location] error: {e}")
        return {'location': '', 'confidence': 0.0, 'reasoning': str(e)}


# ═════════════════════════════════════════════════════════════════════════════
# Geocoding helpers
# ═════════════════════════════════════════════════════════════════════════════

def _geocode(location_text: str) -> dict:
    """Converts free-text location to structured address via Nominatim."""
    if not location_text:
        return {}
    try:
        query = (location_text if re.search(r'\bindia\b', location_text, re.IGNORECASE)
                else location_text + ', India')
        loc = geolocator.geocode(query, language='en', timeout=10)
        if loc:
            return {
                'display_name': loc.address,
                'latitude':     loc.latitude,
                'longitude':    loc.longitude,
            }
    except GeocoderTimedOut:
        print("  [geocode] timed out")
    except Exception as e:
        print(f"  [geocode] error: {e}")
    return {}


def _parse_district_state(location_text: str, geocoded: dict) -> tuple:
    """
    Extracts (district, state) from Nominatim display_name.
    Falls back to splitting raw location_text if geocoding returned nothing.
    """
    district, state = '', ''

    if geocoded.get('display_name'):
        parts     = [p.strip() for p in geocoded['display_name'].split(',')]
        india_idx = next(
            (i for i, p in enumerate(parts) if p.lower() == 'india'), -1
        )
        if india_idx > 0:
            state    = parts[india_idx - 1] if india_idx >= 1 else ''
            district = parts[india_idx - 2] if india_idx >= 2 else ''
            # ADD: reject if district resolved to 'India' (wrap-around)
            if district.lower() == 'india':
                district = ''

    # Fallback — split raw text
    if not state and location_text:
        parts = [p.strip() for p in location_text.split(',')]
        if len(parts) >= 2:
            district, state = parts[0], parts[1]
        elif len(parts) == 1:
            district = parts[0]

    # Guard: Nominatim sometimes returns a PIN code as state
    if state.isdigit():
        state = ''

    return district, state


# ═════════════════════════════════════════════════════════════════════════════
# Agent 2 — public interface
# ═════════════════════════════════════════════════════════════════════════════

def resolve_location(
    frame_b64:      str,
    user_location:  str = '',
    social_caption: str = '',
    transcript:     str = '',
) -> dict:
    """
    AGENT 2 — Weighted Location Resolver.

    Three signals, each scaled by their own confidence:
        1. User-provided text / map pin  → weight 0.85 (fixed, most trusted)
        2. Transcript speech extraction  → weight 0.60 × transcript_confidence
        3. Groq Vision frame analysis    → weight 0.15 × vision_confidence

    The signal with the highest effective weight supplies final_location.
    Confidence is normalised against max possible weight (0.85).

    Args:
        frame_b64:      base64 JPEG of best frame (from Agent 0)
        user_location:  location string typed / pinned by user
        social_caption: post caption from yt-dlp (optional)
        transcript:     English transcript (from Agent 0)

    Returns:
        {
            "state":            str,
            "district":         str,
            "location_label":   str,
            "confidence":       float,
            "dominant_signal":  str,
            "needs_user_input": bool,
        }
    """
    print("\n" + "=" * 55)
    print("AGENT 2 — Location resolution starting...")
    print("=" * 55)

    # ── Collect signals ───────────────────────────────────────────────────────
    vision_result     = _vision_location(frame_b64, social_caption) if frame_b64 else \
                        {'location': '', 'confidence': 0.0, 'reasoning': ''}
    transcript_result = _transcript_location(transcript)

    vision_weight     = _WEIGHT_VISION     * float(vision_result.get('confidence', 0.0))
    transcript_weight = _WEIGHT_TRANSCRIPT * float(transcript_result.get('confidence', 0.0))
    user_weight       = _WEIGHT_USER if user_location.strip() else 0.0

    signals = {
        'user':       (user_location.strip(),                    user_weight),
        'transcript': (transcript_result.get('location', ''),   transcript_weight),
        'vision':     (vision_result.get('location', ''),       vision_weight),
    }

    print(f"  user       weight={user_weight:.3f}  → \"{user_location}\"")
    print(f"  transcript weight={transcript_weight:.3f}  "
          f"→ \"{transcript_result.get('location', '')}\"")
    print(f"  vision     weight={vision_weight:.3f}  "
          f"→ \"{vision_result.get('location', '')}\"")

    total_weight = sum(w for _, w in signals.values())

    # ── No signal at all ──────────────────────────────────────────────────────
    if total_weight == 0:
        print("  No location signal — needs user input")
        return {
            'state': '', 'district': '', 'location_label': '',
            'confidence': 0.0, 'dominant_signal': 'none',
            'needs_user_input': True,
        }

    # ── Pick dominant signal ──────────────────────────────────────────────────
    dominant       = max(signals, key=lambda k: signals[k][1])
    final_location = signals[dominant][0]

    # If dominant returned an empty string, fall back to next best non-empty
    if not final_location:
        for key in sorted(signals, key=lambda k: signals[k][1], reverse=True):
            if signals[key][0]:
                final_location = signals[key][0]
                dominant       = key
                break

    # ADD THIS:
    if not final_location:
        return {
            'state': '', 'district': '', 'location_label': '',
            'confidence': 0.0, 'dominant_signal': dominant,
            'needs_user_input': True,
        }

    # ── Mismatch check — prompt user to confirm if signals disagree ───────────
    needs_user_input = False
    if user_location.strip() and dominant != 'user':
        u_words = set(user_location.lower().split())
        d_words = set(final_location.lower().split())
        if not u_words.intersection(d_words):
            needs_user_input = True
            print(f"  ⚠ MISMATCH: user=\"{user_location}\" "
                  f"vs {dominant}=\"{final_location}\"")

    # ── Geocode → structured district + state ────────────────────────────────
    geocoded         = _geocode(final_location)
    district, state  = _parse_district_state(final_location, geocoded)

    location_label = (
        f"{district}, {state}".strip(', ')
        if (district or state)
        else final_location
    )

    # Confidence: dominant signal's effective weight / max possible weight
    dominant_weight = signals[dominant][1]
    confidence      = round(dominant_weight / _MAX_WEIGHT, 3)

    print(f"\n  final_location : \"{final_location}\"")
    print(f"  district       : \"{district}\"")
    print(f"  state          : \"{state}\"")
    print(f"  dominant       : {dominant}  (confidence={confidence:.3f})")
    print("=" * 55)

    return {
        'state':            state,
        'district':         district,
        'location_label':   location_label,
        'confidence':       confidence,
        'dominant_signal':  dominant,
        'needs_user_input': needs_user_input,
    }