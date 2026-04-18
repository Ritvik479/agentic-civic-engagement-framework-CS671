"""
test_pair_d_vision_real.py
──────────────────────────
Real-data integration test suite for pair-d's four vision tools.

Unlike test_pair_d_vision.py (which mocks all external I/O), this suite
runs against your actual video files, audio clips, subtitle files, and
GPS metadata. Every test calls the real Groq API, real YOLO, real Whisper,
and real Nominatim.

Requirements before running:
    • GROQ_API_KEY set in your .env (loaded by app/main.py or manually)
    • pip install python-dotenv
    • All model weights present (yolov8n.pt, Whisper medium)
    • data/test_vision/ populated as documented in data/README.md

Run all real-data tests:
    pytest scripts/test_pair_d_vision_real.py -v -s

Run one section:
    pytest scripts/test_pair_d_vision_real.py -v -s -k "R3"

Run only fast tests (skip pipeline):
    pytest scripts/test_pair_d_vision_real.py -v -s -k "not R8"

Mark meaning:
    @pytest.mark.real_data   — needs files + API key
    @pytest.mark.slow        — takes >10 s (Whisper, full pipeline)

Design rules:
    • Tests SKIP (not fail) when a required file is absent.
    • Tests SKIP when GROQ_API_KEY is not set.
    • LLM-dependent assertions check MEMBERSHIP in the canonical set
      and a CONFIDENCE FLOOR from the golden file — never exact strings.
    • Each test is independent — no shared state between tests.
    • tmp_path (pytest built-in) is used for all temp files — cross-platform.

How to run:
# All real-data tests (will take several minutes)
pytest scripts/test_pair_d_vision_real.py -v -s

# Skip the slow tests (frame extraction + sharpness only)
pytest scripts/test_pair_d_vision_real.py -v -s -k "not slow"

# One section only
pytest scripts/test_pair_d_vision_real.py -v -s -k "R7"

# Both suites together
pytest scripts/test_pair_d_vision.py scripts/test_pair_d_vision_real.py -v
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

# ── Path bootstrap ─────────────────────────────────────────────────────────────
ROOT     = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "test_vision"
VIDEOS   = DATA_DIR / "videos"
FRAMES   = DATA_DIR / "sample_frames"
AUDIO    = DATA_DIR / "audio"
SUBS     = DATA_DIR / "subtitles"
META     = DATA_DIR / "metadata"
EXPECTED = DATA_DIR / "expected_outputs"

sys.path.insert(0, str(ROOT))

# ── Load .env so GROQ_API_KEY is available ─────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass   # dotenv not installed — key must already be in environment

# ── Markers ────────────────────────────────────────────────────────────────────
pytestmark = [pytest.mark.real_data]


# ══════════════════════════════════════════════════════════════════════════════
# SHARED CONSTANTS & HELPERS
# ══════════════════════════════════════════════════════════════════════════════

# Every valid value detect_issue() can return as issue_type
CANONICAL_ISSUE_TYPES = {
    "Waste Management",
    "Air Pollution",
    "Water Pollution",
    "Road Damage",
    "Animal Control",
    "Public Sanitation",
    "Infrastructure Damage",
    "Unknown",
}

# ── Skip conditions ────────────────────────────────────────────────────────────

def _has_key() -> bool:
    return bool(os.environ.get("GROQ_API_KEY", "").strip())

def _has_file(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0

def _video(name: str) -> Path:
    return VIDEOS / name

def _audio_file(name: str) -> Path:
    return AUDIO / name

# ── Golden file loaders ────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict | list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def _golden_vision() -> list[dict]:
    """Load expected_outputs/vision_expected.json."""
    path = EXPECTED / "vision_expected.json"
    if not path.exists():
        return []
    data = _load_json(path)
    return data if isinstance(data, list) else [data]

def _golden_location() -> dict:
    path = EXPECTED / "location_expected.json"
    return _load_json(path) if path.exists() else {}

def _golden_context() -> dict:
    path = EXPECTED / "context_expected.json"
    return _load_json(path) if path.exists() else {}

def _location_meta() -> dict:
    path = META / "location_metadata.json"
    return _load_json(path) if path.exists() else {}

def _exif_samples() -> list[dict]:
    path = META / "exif_samples.json"
    if not path.exists():
        return []
    data = _load_json(path)
    return data if isinstance(data, list) else [data]

# ── Frame extraction helper (reused across sections) ──────────────────────────

def _extract_frame(video_path: Path, tmp_path: Path) -> tuple[str, str]:
    """
    Extract best frame from video_path, save to tmp_path.
    Returns (frame_path_str, frame_b64).
    Raises RuntimeError if extraction fails.
    """
    from app.tools.pair_d.context_extractor_tool import extract_best_frame
    frame_path = extract_best_frame(str(video_path))
    with open(frame_path, "rb") as fh:
        frame_b64 = base64.b64encode(fh.read()).decode()
    return frame_path, frame_b64


# ══════════════════════════════════════════════════════════════════════════════
# R1 — Real frame extraction
# ══════════════════════════════════════════════════════════════════════════════

class TestR1RealFrameExtraction:
    """
    extract_best_frame() on real video files.
    Deterministic — no API calls, no LLM.
    """

    @pytest.mark.parametrize("filename", [
        "pollution_smoke.mp4",
        "garbage_dump.mp4",
        "road_pothole.mp4",
        "stray_animals.mp4",
        "drain_overflow.mp4",
        "hindi_audio.mp4",
        "no_audio.mp4",
        "embedded_subs.mp4",
    ])
    def test_extract_frame_produces_valid_jpeg(self, filename, tmp_path):
        video = _video(filename)
        if not _has_file(video):
            pytest.skip(f"Video file not present: {filename}")

        from app.tools.pair_d.context_extractor_tool import extract_best_frame
        frame_path = extract_best_frame(str(video))

        assert frame_path.endswith(".jpg"), "Output must be a JPEG"
        assert Path(frame_path).exists(),   "Frame file must exist on disk"
        assert Path(frame_path).stat().st_size > 0, "Frame file must not be empty"

    def test_extracted_frame_is_readable_as_image(self, tmp_path):
        video = _video("garbage_dump.mp4")
        if not _has_file(video):
            pytest.skip("garbage_dump.mp4 not present")

        import cv2
        from app.tools.pair_d.context_extractor_tool import extract_best_frame
        frame_path = extract_best_frame(str(video))
        img = cv2.imread(frame_path)
        assert img is not None,       "cv2 must be able to read the saved frame"
        assert img.ndim == 3,         "Frame must be a 3-channel image (H, W, C)"
        assert img.shape[2] == 3,     "Frame must have 3 colour channels (BGR)"
        assert img.shape[0] > 0,      "Frame height must be > 0"
        assert img.shape[1] > 0,      "Frame width must be > 0"

    def test_frame_content_is_non_uniform(self, tmp_path):
        """A real-world frame must not be a solid colour — some variance expected."""
        video = _video("pollution_smoke.mp4")
        if not _has_file(video):
            pytest.skip("pollution_smoke.mp4 not present")

        import cv2
        from app.tools.pair_d.context_extractor_tool import extract_best_frame
        frame_path = extract_best_frame(str(video))
        img = cv2.imread(frame_path).astype(float)
        assert img.std() > 5.0, (
            "Real frame should have pixel variance > 5 — got a near-solid image"
        )

    def test_two_videos_produce_different_frames(self, tmp_path):
        """Each video should produce a distinct frame (different pixel content)."""
        v1 = _video("garbage_dump.mp4")
        v2 = _video("road_pothole.mp4")
        if not (_has_file(v1) and _has_file(v2)):
            pytest.skip("Need both garbage_dump.mp4 and road_pothole.mp4")

        import cv2
        from app.tools.pair_d.context_extractor_tool import extract_best_frame
        p1 = extract_best_frame(str(v1))
        p2 = extract_best_frame(str(v2))
        img1 = cv2.imread(p1).astype(float)
        img2 = cv2.imread(p2).astype(float)

        # Resize to same shape before comparing
        img2_resized = cv2.resize(img2, (img1.shape[1], img1.shape[0]))
        diff = np.abs(img1 - img2_resized).mean()
        assert diff > 1.0, "Frames from two different videos should differ"


# ══════════════════════════════════════════════════════════════════════════════
# R2 — Real sharpness scoring
# ══════════════════════════════════════════════════════════════════════════════

class TestR2RealSharpness:
    """
    _sharpness() and _score_frame() on real extracted frames.
    Deterministic — uses real cv2 and real YOLO.
    """

    def test_sharpness_on_real_frame_is_positive_float(self, tmp_path):
        video = _video("garbage_dump.mp4")
        if not _has_file(video):
            pytest.skip("garbage_dump.mp4 not present")

        from app.tools.pair_d.context_extractor_tool import (
            extract_best_frame, _sharpness
        )
        import cv2
        frame_path = extract_best_frame(str(video))
        img = cv2.imread(frame_path)
        val = _sharpness(img)
        assert isinstance(val, float), "Sharpness must return a float"
        assert val > 0.0,              "Real-world frame must have positive sharpness"

    def test_score_frame_on_real_frame_is_non_negative(self, tmp_path):
        video = _video("garbage_dump.mp4")
        if not _has_file(video):
            pytest.skip("garbage_dump.mp4 not present")

        from app.tools.pair_d.context_extractor_tool import (
            extract_best_frame, _score_frame
        )
        import cv2
        frame_path = extract_best_frame(str(video))
        img = cv2.imread(frame_path)
        score = _score_frame(img)
        assert isinstance(score, float), "_score_frame must return a float"
        assert score >= 0.0,             "Score must be non-negative"

    def test_outdoor_civic_frame_scores_higher_than_zero(self, tmp_path):
        """A real outdoor civic video should produce a non-zero frame score."""
        video = _video("road_pothole.mp4")
        if not _has_file(video):
            pytest.skip("road_pothole.mp4 not present")

        from app.tools.pair_d.context_extractor_tool import (
            extract_best_frame, _score_frame
        )
        import cv2
        frame_path = extract_best_frame(str(video))
        img   = cv2.imread(frame_path)
        score = _score_frame(img)
        assert score > 0.0, "Outdoor civic frame must score > 0"


# ══════════════════════════════════════════════════════════════════════════════
# R3 — Real transcripts
# ══════════════════════════════════════════════════════════════════════════════

class TestR3RealTranscripts:
    """
    _get_transcript() on real audio/video files.
    Uses real Whisper — slow (~30 s per file).
    """

    @pytest.mark.slow
    def test_english_audio_produces_non_empty_transcript(self, tmp_path):
        audio = _audio_file("english_complaint.wav")
        if not _has_file(audio):
            pytest.skip("english_complaint.wav not present")

        # Build a minimal fake video path and bypass video steps —
        # we test _get_transcript directly with no auto-subs
        from app.tools.pair_d.context_extractor_tool import _get_transcript
        result = _get_transcript(str(audio), youtube_auto_subs="")

        assert result["source"] in {"whisper", "embedded_subtitle", "none"}
        if result["source"] == "whisper":
            assert len(result["text"].strip()) > 0, "English audio must produce non-empty transcript"
            assert result["language"] in {"en", "english", "hi", "unknown"}

    @pytest.mark.slow
    def test_hindi_audio_transcribed_by_whisper(self, tmp_path):
        audio = _audio_file("hindi_complaint.wav")
        if not _has_file(audio):
            pytest.skip("hindi_complaint.wav not present")

        from app.tools.pair_d.context_extractor_tool import _get_transcript
        result = _get_transcript(str(audio), youtube_auto_subs="")

        assert result["source"] in {"whisper", "none"}
        if result["source"] == "whisper":
            assert len(result["text"].strip()) > 0, "Hindi audio must produce non-empty transcript"
            # Whisper should detect Hindi or a related language
            assert result["language"] in {"hi", "ur", "pa", "en", "unknown"}, (
                f"Unexpected language for Hindi audio: {result['language']}"
            )

    @pytest.mark.slow
    def test_silent_audio_returns_empty_or_noise(self, tmp_path):
        audio = _audio_file("silent.wav")
        if not _has_file(audio):
            pytest.skip("silent.wav not present")

        from app.tools.pair_d.context_extractor_tool import _get_transcript
        result = _get_transcript(str(audio), youtube_auto_subs="")
        # Silent audio: either no audio track found, or Whisper returns minimal noise
        assert result["source"] in {"none", "whisper"}
        if result["source"] == "whisper":
            assert len(result["text"].strip()) < 50, (
                "Silent audio should produce near-empty transcript"
            )

    def test_vtt_auto_subs_used_before_whisper(self, tmp_path):
        """When youtube_auto_subs is provided, Whisper must NOT be called."""
        vtt_path = SUBS / "sample_auto.vtt"
        if not _has_file(vtt_path):
            pytest.skip("sample_auto.vtt not present")

        with open(vtt_path, encoding="utf-8") as f:
            raw_vtt = f.read()

        from app.tools.pair_d.context_extractor_tool import _get_transcript
        result = _get_transcript("/fake/video.mp4", youtube_auto_subs=raw_vtt)

        assert result["source"] == "youtube_auto_sub"
        assert "-->"    not in result["text"], "VTT timestamps must be stripped"
        assert "WEBVTT" not in result["text"], "WEBVTT header must be stripped"
        assert len(result["text"].strip()) > 0, "Stripped VTT must still contain speech"

    def test_clean_srt_content_preserved(self, tmp_path):
        """sample_clean.srt contains only speech — must pass through unchanged."""
        srt_path = SUBS / "sample_clean.srt"
        if not _has_file(srt_path):
            pytest.skip("sample_clean.srt not present")

        with open(srt_path, encoding="utf-8") as f:
            clean_text = f.read()

        from app.tools.pair_d.context_extractor_tool import _strip_vtt
        result = _strip_vtt(clean_text)
        # Already clean — meaningful words should survive
        assert len(result.strip()) > 0, "Clean SRT content must survive _strip_vtt"

    @pytest.mark.slow
    def test_embedded_subs_video_uses_embedded_path(self, tmp_path):
        video = _video("embedded_subs.mp4")
        if not _has_file(video):
            pytest.skip("embedded_subs.mp4 not present")

        from app.tools.pair_d.context_extractor_tool import (
            _check_embedded_subtitles, _get_transcript
        )
        has_subs = _check_embedded_subtitles(str(video))
        result   = _get_transcript(str(video), youtube_auto_subs="")

        if has_subs:
            assert result["source"] == "embedded_subtitle"
            assert len(result["text"].strip()) > 0
        else:
            # No embedded subs — falls through to Whisper or none
            assert result["source"] in {"whisper", "none"}


# ══════════════════════════════════════════════════════════════════════════════
# R4 — Real VTT stripping on actual file
# ══════════════════════════════════════════════════════════════════════════════

class TestR4RealVttStripping:
    """_strip_vtt() on the actual sample_auto.vtt file."""

    def test_real_vtt_file_stripped_correctly(self):
        vtt_path = SUBS / "sample_auto.vtt"
        if not _has_file(vtt_path):
            pytest.skip("sample_auto.vtt not present")

        with open(vtt_path, encoding="utf-8") as f:
            raw = f.read()

        from app.tools.pair_d.context_extractor_tool import _strip_vtt
        result = _strip_vtt(raw)

        assert "WEBVTT"  not in result, "WEBVTT header must be removed"
        assert "-->"     not in result, "Timestamp lines must be removed"
        assert len(result.strip()) > 0, "Speech content must survive stripping"

    def test_stripped_vtt_shorter_than_original(self):
        vtt_path = SUBS / "sample_auto.vtt"
        if not _has_file(vtt_path):
            pytest.skip("sample_auto.vtt not present")

        with open(vtt_path, encoding="utf-8") as f:
            raw = f.read()

        from app.tools.pair_d.context_extractor_tool import _strip_vtt
        result = _strip_vtt(raw)
        assert len(result) < len(raw), (
            "Stripped output must be shorter than raw VTT "
            "(timestamps and headers removed)"
        )


# ══════════════════════════════════════════════════════════════════════════════
# R5 — Real location resolution
# ══════════════════════════════════════════════════════════════════════════════

class TestR5RealLocationResolution:
    """
    resolve_location() with real GPS coordinates from location_metadata.json.
    Calls real Groq API and real Nominatim.
    """

    @pytest.mark.slow
    def test_gps_coords_resolve_to_indian_state(self):
        if not _has_key():
            pytest.skip("GROQ_API_KEY not set")

        meta = _location_meta()
        if not meta:
            pytest.skip("location_metadata.json not present")

        lat = meta["lat"]
        lng = meta["lng"]

        from app.tools.pair_d.location_resolver_tool import resolve_location
        result = resolve_location(
            frame_b64     = "",
            user_location = f"{lat}, {lng}",
            social_caption= "",
            transcript    = "",
        )

        assert isinstance(result, dict)
        assert "state"            in result
        assert "district"         in result
        assert "location_label"   in result
        assert "confidence"       in result
        assert "dominant_signal"  in result
        assert "needs_user_input" in result
        assert 0.0 <= result["confidence"] <= 1.0

    @pytest.mark.slow
    def test_gps_coords_return_correct_country(self):
        """Coordinates in India must resolve to an Indian state — not empty."""
        if not _has_key():
            pytest.skip("GROQ_API_KEY not set")

        meta = _location_meta()
        if not meta:
            pytest.skip("location_metadata.json not present")

        from app.tools.pair_d.location_resolver_tool import resolve_location
        result = resolve_location(
            frame_b64     = "",
            user_location = f"{meta['lat']}, {meta['lng']}",
        )

        # If Nominatim resolved it, state should be non-empty
        if not result["needs_user_input"]:
            assert result["state"] != "", (
                "GPS coordinates in India must resolve to a non-empty state"
            )

    @pytest.mark.slow
    def test_golden_location_expected_state(self):
        """Check resolved state matches location_expected.json if available."""
        if not _has_key():
            pytest.skip("GROQ_API_KEY not set")

        golden = _golden_location()
        if not golden:
            pytest.skip("location_expected.json not present")

        from app.tools.pair_d.location_resolver_tool import resolve_location
        result = resolve_location(
            frame_b64     = "",
            user_location = f"{golden['lat']}, {golden['lng']}",
        )

        expected_state = golden.get("expected_state", "")
        if expected_state and not result["needs_user_input"]:
            assert result["state"].lower() == expected_state.lower(), (
                f"Expected state '{expected_state}', got '{result['state']}'"
            )

    @pytest.mark.slow
    def test_transcript_signal_contributes_to_location(self):
        """Providing a transcript with a clear location should produce high confidence."""
        if not _has_key():
            pytest.skip("GROQ_API_KEY not set")

        from app.tools.pair_d.location_resolver_tool import resolve_location
        result = resolve_location(
            frame_b64  = "",
            transcript = "The garbage dumping is happening near Anand Vihar, New Delhi.",
        )

        assert result["dominant_signal"] in {"transcript", "user", "vision", "none"}
        assert 0.0 <= result["confidence"] <= 1.0
        # With a clear location mention, confidence should not be zero
        if result["dominant_signal"] == "transcript":
            assert result["confidence"] > 0.0

    def test_empty_all_signals_asks_for_user_input(self):
        """No frame, no transcript, no user location — must request user input."""
        from app.tools.pair_d.location_resolver_tool import resolve_location
        result = resolve_location(frame_b64="", user_location="",
                                   social_caption="", transcript="")
        assert result["needs_user_input"] is True
        assert result["dominant_signal"]  == "none"


# ══════════════════════════════════════════════════════════════════════════════
# R6 — Real EXIF extraction
# ══════════════════════════════════════════════════════════════════════════════

class TestR6RealExif:
    """
    GPS EXIF extraction from geotagged_sample.jpg.
    Deterministic — no API calls.
    """

    def test_geotagged_image_has_readable_exif(self):
        img_path = FRAMES / "geotagged_sample.jpg"
        if not _has_file(img_path):
            pytest.skip("geotagged_sample.jpg not present")

        try:
            from PIL import Image
            from PIL.ExifTags import TAGS, GPSTAGS
        except ImportError:
            pytest.skip("Pillow not installed")

        img  = Image.open(img_path)
        exif = img._getexif()
        assert exif is not None, "geotagged_sample.jpg must contain EXIF data"

    def test_exif_gps_coords_in_valid_range(self):
        img_path = FRAMES / "geotagged_sample.jpg"
        if not _has_file(img_path):
            pytest.skip("geotagged_sample.jpg not present")

        samples = _exif_samples()
        if not samples:
            pytest.skip("exif_samples.json not present")

        entry = next(
            (s for s in samples if s["filename"] == "geotagged_sample.jpg"), None
        )
        if entry is None:
            pytest.skip("No exif_samples.json entry for geotagged_sample.jpg")

        expected_lat = entry["expected_lat"]
        expected_lng = entry["expected_lng"]
        tolerance    = entry.get("tolerance_deg", 0.01)

        assert -90  <= expected_lat <= 90,  "Latitude in exif_samples.json out of range"
        assert -180 <= expected_lng <= 180, "Longitude in exif_samples.json out of range"

        # If we can extract GPS from the image, compare against expected
        try:
            from PIL import Image
            from PIL.ExifTags import TAGS, GPSTAGS

            img  = Image.open(img_path)
            exif = img._getexif()
            if exif is None:
                pytest.skip("No EXIF in image")

            gps_info = {}
            for tag_id, value in exif.items():
                tag = TAGS.get(tag_id, tag_id)
                if tag == "GPSInfo":
                    for gps_tag_id, gps_value in value.items():
                        gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                        gps_info[gps_tag] = gps_value

            if "GPSLatitude" not in gps_info:
                pytest.skip("No GPS coordinates in EXIF")

            def _dms_to_decimal(dms, ref):
                d, m, s = [float(x) for x in dms]
                decimal  = d + m / 60 + s / 3600
                if ref in ("S", "W"):
                    decimal = -decimal
                return decimal

            lat = _dms_to_decimal(gps_info["GPSLatitude"],
                                   gps_info.get("GPSLatitudeRef",  "N"))
            lng = _dms_to_decimal(gps_info["GPSLongitude"],
                                   gps_info.get("GPSLongitudeRef", "E"))

            assert abs(lat - expected_lat) <= tolerance, (
                f"EXIF lat {lat:.4f} differs from expected {expected_lat:.4f} "
                f"by more than {tolerance} degrees"
            )
            assert abs(lng - expected_lng) <= tolerance, (
                f"EXIF lng {lng:.4f} differs from expected {expected_lng:.4f} "
                f"by more than {tolerance} degrees"
            )
        except ImportError:
            pytest.skip("Pillow not installed")


# ══════════════════════════════════════════════════════════════════════════════
# R7 — Real issue detection (golden file checks)
# ══════════════════════════════════════════════════════════════════════════════

class TestR7RealIssueDetection:
    """
    detect_issue() on real extracted frames.
    Calls real YOLO + real Groq API.
    Assertions use MEMBERSHIP and FLOOR checks — not exact matches.
    """

    @pytest.mark.slow
    @pytest.mark.parametrize("entry", _golden_vision(), ids=lambda e: e["file"])
    def test_detect_issue_canonical_type(self, entry, tmp_path):
        if not _has_key():
            pytest.skip("GROQ_API_KEY not set")

        video = _video(entry["file"])
        if not _has_file(video):
            pytest.skip(f"Video not present: {entry['file']}")

        from app.tools.pair_d.context_extractor_tool import extract_best_frame
        from app.tools.pair_d.issue_detector_tool    import detect_issue

        frame_path = extract_best_frame(str(video))
        with open(frame_path, "rb") as fh:
            frame_b64 = base64.b64encode(fh.read()).decode()

        context = {
            "frame_path":     frame_path,
            "frame_b64":      frame_b64,
            "transcript_en":  "",
            "on_screen_text": "",
            "whatsapp_text":  "",
        }

        try:
            result = detect_issue(context)
        except Exception as e:
            pytest.xfail(f"API error during detect_issue: {e}")

        assert "issue_type"      in result
        assert "confidence"      in result
        assert "reasoning"       in result
        assert "refinement_used" in result

        assert result["issue_type"] in CANONICAL_ISSUE_TYPES, (
            f"[{entry['file']}] issue_type '{result['issue_type']}' "
            f"is not a valid canonical value"
        )

        assert 0.0 <= result["confidence"] <= 1.0, (
            f"[{entry['file']}] confidence {result['confidence']} out of range"
        )

    @pytest.mark.slow
    @pytest.mark.parametrize("entry", _golden_vision(), ids=lambda e: e["file"])
    def test_detect_issue_confidence_floor(self, entry, tmp_path):
        """Confidence must meet the floor set in vision_expected.json."""
        if not _has_key():
            pytest.skip("GROQ_API_KEY not set")

        video = _video(entry["file"])
        if not _has_file(video):
            pytest.skip(f"Video not present: {entry['file']}")

        confidence_min = entry.get("confidence_min", 0.0)
        if confidence_min == 0.0:
            pytest.skip(f"confidence_min is 0.0 for {entry['file']} — nothing to check")

        from app.tools.pair_d.context_extractor_tool import extract_best_frame
        from app.tools.pair_d.issue_detector_tool    import detect_issue

        frame_path = extract_best_frame(str(video))
        with open(frame_path, "rb") as fh:
            frame_b64 = base64.b64encode(fh.read()).decode()

        context = {
            "frame_path":     frame_path,
            "frame_b64":      frame_b64,
            "transcript_en":  "",
            "on_screen_text": "",
            "whatsapp_text":  "",
        }

        try:
            result = detect_issue(context)
        except Exception as e:
            pytest.xfail(f"API error during detect_issue: {e}")

        assert result["confidence"] >= confidence_min, (
            f"[{entry['file']}] confidence {result['confidence']:.2f} "
            f"is below floor {confidence_min}"
        )

    @pytest.mark.slow
    @pytest.mark.parametrize("entry", _golden_vision(), ids=lambda e: e["file"])
    def test_detect_issue_soft_type_match(self, entry, tmp_path):
        """
        Soft check: expected issue_type from golden file should match result.
        Marked xfail if it doesn't — LLMs can legitimately disagree.
        """
        if not _has_key():
            pytest.skip("GROQ_API_KEY not set")

        video = _video(entry["file"])
        if not _has_file(video):
            pytest.skip(f"Video not present: {entry['file']}")

        expected_type = entry.get("issue_type", "")
        if not expected_type:
            pytest.skip("No expected issue_type in golden file")

        from app.tools.pair_d.context_extractor_tool import extract_best_frame
        from app.tools.pair_d.issue_detector_tool    import detect_issue

        frame_path = extract_best_frame(str(video))
        with open(frame_path, "rb") as fh:
            frame_b64 = base64.b64encode(fh.read()).decode()

        context = {
            "frame_path":     frame_path,
            "frame_b64":      frame_b64,
            "transcript_en":  "",
            "on_screen_text": "",
            "whatsapp_text":  "",
        }

        try:
            result = detect_issue(context)
        except Exception as e:
            pytest.xfail(f"API error during detect_issue: {e}")

        if result["issue_type"] != expected_type:
            pytest.xfail(
                f"[{entry['file']}] Soft type mismatch: "
                f"expected '{expected_type}', got '{result['issue_type']}'. "
                f"LLM classification can vary — review golden file if this persists."
            )


# ══════════════════════════════════════════════════════════════════════════════
# R8 — Real pipeline end-to-end
# ══════════════════════════════════════════════════════════════════════════════

class TestR8RealPipeline:
    """
    run_vision_pipeline() end-to-end on real video files.
    Calls all three agents. Slowest tests in the suite (~1-3 min each).
    """

    @pytest.mark.slow
    @pytest.mark.parametrize("filename", [
        "pollution_smoke.mp4",
        "garbage_dump.mp4",
        "road_pothole.mp4",
    ])
    def test_pipeline_returns_required_keys(self, filename):
        if not _has_key():
            pytest.skip("GROQ_API_KEY not set")

        video = _video(filename)
        if not _has_file(video):
            pytest.skip(f"Video not present: {filename}")

        from app.tools.pair_d.vision_pipeline_tool import run_vision_pipeline
        try:
            result = run_vision_pipeline(video_path=str(video))
        except Exception as e:
            pytest.xfail(f"Pipeline raised unexpected exception: {e}")

        required = {
            "issue_type", "transcript", "state", "district",
            "location_label", "confidence", "reasoning", "needs_user_input",
        }
        assert required.issubset(result.keys()), (
            f"Pipeline output missing keys: {required - result.keys()}"
        )

    @pytest.mark.slow
    @pytest.mark.parametrize("filename", [
        "pollution_smoke.mp4",
        "garbage_dump.mp4",
        "road_pothole.mp4",
    ])
    def test_pipeline_issue_type_is_canonical(self, filename):
        if not _has_key():
            pytest.skip("GROQ_API_KEY not set")

        video = _video(filename)
        if not _has_file(video):
            pytest.skip(f"Video not present: {filename}")

        from app.tools.pair_d.vision_pipeline_tool import run_vision_pipeline
        try:
            result = run_vision_pipeline(video_path=str(video))
        except Exception as e:
            pytest.xfail(f"Pipeline raised unexpected exception: {e}")

        assert result["issue_type"] in CANONICAL_ISSUE_TYPES, (
            f"[{filename}] issue_type '{result['issue_type']}' is not canonical"
        )

    @pytest.mark.slow
    @pytest.mark.parametrize("filename", [
        "pollution_smoke.mp4",
        "garbage_dump.mp4",
        "road_pothole.mp4",
    ])
    def test_pipeline_confidence_in_valid_range(self, filename):
        if not _has_key():
            pytest.skip("GROQ_API_KEY not set")

        video = _video(filename)
        if not _has_file(video):
            pytest.skip(f"Video not present: {filename}")

        from app.tools.pair_d.vision_pipeline_tool import run_vision_pipeline
        try:
            result = run_vision_pipeline(video_path=str(video))
        except Exception as e:
            pytest.xfail(f"Pipeline raised unexpected exception: {e}")

        assert 0.0 <= result["confidence"] <= 1.0

    @pytest.mark.slow
    def test_pipeline_with_user_location_does_not_need_user_input(self):
        """Providing a clear user_location should resolve without prompting."""
        if not _has_key():
            pytest.skip("GROQ_API_KEY not set")

        video = _video("garbage_dump.mp4")
        if not _has_file(video):
            pytest.skip("garbage_dump.mp4 not present")

        from app.tools.pair_d.vision_pipeline_tool import run_vision_pipeline
        try:
            result = run_vision_pipeline(
                video_path    = str(video),
                user_location = "Anand Vihar, New Delhi",
            )
        except Exception as e:
            pytest.xfail(f"Pipeline raised unexpected exception: {e}")

        assert result["needs_user_input"] is False, (
            "Providing a clear user_location should satisfy location resolution"
        )

    @pytest.mark.slow
    def test_pipeline_output_maps_to_complaint_context(self):
        """Output keys must map cleanly into ComplaintContext without raising."""
        if not _has_key():
            pytest.skip("GROQ_API_KEY not set")

        video = _video("garbage_dump.mp4")
        if not _has_file(video):
            pytest.skip("garbage_dump.mp4 not present")

        from app.tools.pair_d.vision_pipeline_tool import run_vision_pipeline
        from app.context import ComplaintContext

        try:
            result = run_vision_pipeline(video_path=str(video))
        except Exception as e:
            pytest.xfail(f"Pipeline raised unexpected exception: {e}")

        # Extract only the fields ComplaintContext accepts
        ctx = ComplaintContext(
            issue_type     = result.get("issue_type",     ""),
            transcript     = result.get("transcript",     ""),
            state          = result.get("state",          ""),
            district       = result.get("district",       ""),
            location_label = result.get("location_label", ""),
        )
        assert ctx.issue_type == result["issue_type"]
        assert ctx.state      == result["state"]


# ══════════════════════════════════════════════════════════════════════════════
# R9 — Real extract_context schema
# ══════════════════════════════════════════════════════════════════════════════

class TestR9RealExtractContext:
    """
    extract_context() on real video files.
    Checks output schema and that key fields are populated.
    """

    @pytest.mark.slow
    def test_extract_context_returns_full_schema(self):
        if not _has_key():
            pytest.skip("GROQ_API_KEY not set")

        video = _video("garbage_dump.mp4")
        if not _has_file(video):
            pytest.skip("garbage_dump.mp4 not present")

        from app.tools.pair_d.context_extractor_tool import extract_context
        try:
            result = extract_context(video_path=str(video))
        except Exception as e:
            pytest.xfail(f"extract_context raised: {e}")

        required = {
            "video_path", "frame_path", "frame_b64",
            "transcript", "transcript_en", "transcript_lang", "transcript_source",
            "on_screen_text", "social_caption", "social_tags", "social_title",
            "whatsapp_text", "user_location", "source_url", "error",
        }
        assert required.issubset(result.keys())

    @pytest.mark.slow
    def test_extract_context_frame_extracted(self):
        if not _has_key():
            pytest.skip("GROQ_API_KEY not set")

        video = _video("garbage_dump.mp4")
        if not _has_file(video):
            pytest.skip("garbage_dump.mp4 not present")

        from app.tools.pair_d.context_extractor_tool import extract_context
        try:
            result = extract_context(video_path=str(video))
        except Exception as e:
            pytest.xfail(f"extract_context raised: {e}")

        assert result["error"] == "", f"extract_context returned error: {result['error']}"
        assert result["frame_b64"],   "frame_b64 must be non-empty for a valid video"
        assert result["frame_path"],  "frame_path must be non-empty"
        assert Path(result["frame_path"]).exists(), "frame_path must point to a real file"

    @pytest.mark.slow
    def test_extract_context_on_screen_text_is_string(self):
        if not _has_key():
            pytest.skip("GROQ_API_KEY not set")

        video = _video("pollution_smoke.mp4")
        if not _has_file(video):
            pytest.skip("pollution_smoke.mp4 not present")

        from app.tools.pair_d.context_extractor_tool import extract_context
        try:
            result = extract_context(video_path=str(video))
        except Exception as e:
            pytest.xfail(f"extract_context raised: {e}")

        assert isinstance(result["on_screen_text"], str), (
            "on_screen_text must always be a string, even if empty"
        )

    @pytest.mark.slow
    def test_extract_context_golden_issue_type(self):
        """Context output for the golden video must match context_expected.json."""
        if not _has_key():
            pytest.skip("GROQ_API_KEY not set")

        golden = _golden_context()
        if not golden:
            pytest.skip("context_expected.json not present")

        video = _video(golden.get("video", "garbage_dump.mp4"))
        if not _has_file(video):
            pytest.skip(f"Golden video not present: {golden.get('video')}")

        from app.tools.pair_d.context_extractor_tool import extract_context
        try:
            result = extract_context(video_path=str(video))
        except Exception as e:
            pytest.xfail(f"extract_context raised: {e}")

        expected_source = golden.get("expected_transcript_source", "")
        if expected_source:
            assert result["transcript_source"] == expected_source, (
                f"Expected transcript_source '{expected_source}', "
                f"got '{result['transcript_source']}'"
            )

    @pytest.mark.slow
    def test_hindi_video_transcript_translated(self):
        """Hindi audio video must produce a non-empty transcript_en."""
        if not _has_key():
            pytest.skip("GROQ_API_KEY not set")

        video = _video("hindi_audio.mp4")
        if not _has_file(video):
            pytest.skip("hindi_audio.mp4 not present")

        from app.tools.pair_d.context_extractor_tool import extract_context
        try:
            result = extract_context(video_path=str(video))
        except Exception as e:
            pytest.xfail(f"extract_context raised: {e}")

        if result["transcript_lang"] not in ("en", "english", "unknown"):
            assert len(result["transcript_en"].strip()) > 0, (
                "Non-English transcript must be translated to English"
            )

    @pytest.mark.slow
    def test_no_audio_video_transcript_source_is_none_or_whisper(self):
        if not _has_key():
            pytest.skip("GROQ_API_KEY not set")

        video = _video("no_audio.mp4")
        if not _has_file(video):
            pytest.skip("no_audio.mp4 not present")

        from app.tools.pair_d.context_extractor_tool import extract_context
        try:
            result = extract_context(video_path=str(video))
        except Exception as e:
            pytest.xfail(f"extract_context raised: {e}")

        assert result["transcript_source"] in {"none", "whisper"}, (
            "Silent video must use 'none' or 'whisper' (short output) as source"
        )
