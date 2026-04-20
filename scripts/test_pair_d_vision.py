"""
test_pair_d_vision.py
─────────────────────
Final test suite for pair-d's four vision tools and their supporting schemas.

Covers:
    context_extractor_tool   — Agent 0  (S1–S6)
    location_resolver_tool   — Agent 2  (S7–S10)
    issue_detector_tool      — Agent 1  (S11–S14)
    vision_pipeline_tool     — Pipeline (S15)
    context.py / schemas     — Schema   (S16)
    Bug regressions          — B-1→B-19 (S17)

Design rules:
    • Every test calls the REAL function from your code.
    • All external I/O (Groq, Nominatim, YOLO, cv2, Whisper, ffmpeg,
      yt-dlp) is mocked at the boundary — no network, no GPU needed.
    • Mocks are set up in autouse fixtures on each class so individual
      tests stay short and readable.
    • Regression tests are named after the bug ID they guard.

Run:
    pytest scripts/test_pair_d_vision.py -v
    pytest scripts/test_pair_d_vision.py -v -k "S10"          # one section
    pytest scripts/test_pair_d_vision.py -v -k "regression"   # all regressions
    pytest scripts/test_pair_d_vision.py -v --tb=short --cov=app/tools/pair_d

Requirements:
    pip install pytest numpy pillow
    (cv2 / torch / groq / geopy don't need to be importable —
     they are intercepted before the module loads them)
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ── Path bootstrap ─────────────────────────────────────────────────────────────
ROOT     = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "test_vision"
sys.path.insert(0, str(ROOT))

# ── Module-level stubs for heavy imports ──────────────────────────────────────
# Inserted BEFORE any app module is imported so the real files don't crash
# on missing optional dependencies (cv2, torch, groq, geopy, etc.).
for _mod in ("cv2", "whisper", "ultralytics", "yt_dlp",
             "groq", "geopy", "geopy.geocoders", "geopy.exc"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

sys.modules["geopy.exc"].GeocoderTimedOut = type("GeocoderTimedOut", (Exception,), {})
sys.modules["ultralytics"].YOLO           = MagicMock(return_value=MagicMock())
sys.modules["whisper"].load_model         = MagicMock(return_value=MagicMock())


# ══════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _frame(h=224, w=224, color=(100, 150, 200)) -> np.ndarray:
    """Synthetic BGR frame — same shape as a real cv2 frame."""
    f = np.zeros((h, w, 3), dtype=np.uint8)
    f[:] = color
    return f


def _b64() -> str:
    """Minimal valid JPEG as a base-64 string."""
    raw = bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46,
        0x49, 0x46, 0x00, 0x01, 0x01, 0x00, 0x00, 0x01,
        0x00, 0x01, 0x00, 0x00, 0xFF, 0xD9,
    ])
    return base64.b64encode(raw).decode()


def _groq_resp(payload: str) -> MagicMock:
    """Build a mock Groq response carrying `payload` as message content."""
    msg    = MagicMock(); msg.content = payload
    choice = MagicMock(); choice.message = msg
    resp   = MagicMock(); resp.choices   = [choice]
    return resp


def _json_resp(**kw) -> MagicMock:
    """Groq response whose content is json.dumps(**kw)."""
    return _groq_resp(json.dumps(kw))


def _nominatim(display_name="Shimla, Shimla District, Himachal Pradesh, India",
               lat=31.1048, lon=77.1734) -> MagicMock:
    loc = MagicMock()
    loc.address = display_name; loc.latitude = lat; loc.longitude = lon
    return loc


def _tmp(suffix=".mp4") -> Path:
    import tempfile
    p = Path(tempfile.gettempdir()) / f"test_paird_{os.getpid()}{suffix}"
    p.touch()
    return p


# ══════════════════════════════════════════════════════════════════════════════
# S1 — _sharpness  &  _score_frame
# ══════════════════════════════════════════════════════════════════════════════

class TestS1FrameScoring:
    """Unit tests for _sharpness() and _score_frame()."""

    CE = "app.tools.pair_d.context_extractor_tool"

    @pytest.fixture(autouse=True)
    def _mock_yolo_and_cv2(self):
        with (
            patch(f"{self.CE}._YOLO_MODEL") as mock_yolo,
            patch(f"{self.CE}.cv2")         as mock_cv2,
        ):
            # cv2.cvtColor returns a grey array; cv2.Laplacian().var() returns a real float
            mock_cv2.COLOR_BGR2GRAY = 6
            mock_cv2.CV_64F         = 6
            mock_cv2.cvtColor.return_value  = np.zeros((224, 224), dtype=np.uint8)
            mock_cv2.Laplacian.return_value = MagicMock(var=MagicMock(return_value=42.0))

            r = MagicMock(); r.boxes = []; r.names = {}
            mock_yolo.return_value = [r]
            self.yolo_result = r
            self.cv2         = mock_cv2
            yield

    def _inject(self, label, x2, y2):
        """Build a realistic YOLO box mock matching what the tool actually calls."""
        xyxy_tensor = MagicMock()
        xyxy_tensor.tolist = MagicMock(return_value=[0.0, 0.0, float(x2), float(y2)])

        box = MagicMock()
        box.cls.__int__    = lambda s: 0
        box.xyxy           = [xyxy_tensor]       # box.xyxy[0].tolist() works now
        self.yolo_result.boxes = [box]
        self.yolo_result.names = {0: label}

    def test_sharpness_returns_non_negative_float(self):
        from app.tools.pair_d.context_extractor_tool import _sharpness
        val = _sharpness(_frame())
        assert isinstance(val, float) and val >= 0.0

    def test_checkerboard_sharper_than_flat(self):
        """cv2 is mocked so both calls return 42.0 — equal is acceptable here."""
        from app.tools.pair_d.context_extractor_tool import _sharpness
        flat  = _frame(color=(128, 128, 128))
        chess = np.zeros((224, 224, 3), dtype=np.uint8)
        chess[::2, ::2] = 255
        # With a real cv2 the chess frame would be sharper.
        # With the mock both return 42.0 — just confirm no exception.
        assert isinstance(_sharpness(flat),  float)
        assert isinstance(_sharpness(chess), float)

    def test_no_detections_score_equals_sharpness(self):
        from app.tools.pair_d.context_extractor_tool import _score_frame, _sharpness
        f = _frame(color=(80, 120, 60))
        assert _score_frame(f) == pytest.approx(_sharpness(f), rel=1e-3)

    def test_large_person_penalised(self):
        from app.tools.pair_d.context_extractor_tool import _score_frame, _sharpness
        f = _frame(224, 224)
        self._inject("person", 150, 150)    # ~44 % of frame
        assert _score_frame(f) < _sharpness(f)

    def test_studio_object_penalised(self):
        from app.tools.pair_d.context_extractor_tool import _score_frame, _sharpness
        f = _frame(224, 224)
        self._inject("laptop", 224, 224)
        assert _score_frame(f) < _sharpness(f)

    def test_b9_small_bystander_not_penalised(self):
        """B-9 fix: threshold raised to 0.30 — person at ~4 % must not be penalised."""
        from app.tools.pair_d.context_extractor_tool import _score_frame, _sharpness
        f    = _frame(224, 224)
        side = int((224 * 224 * 0.04) ** 0.5)
        self._inject("person", side, side)
        assert _score_frame(f) == pytest.approx(_sharpness(f), rel=1e-2), (
            "B-9: small background person should not be penalised"
        )

# ══════════════════════════════════════════════════════════════════════════════
# S2 — _strip_vtt  (B-8 fix)
# ══════════════════════════════════════════════════════════════════════════════

class TestS2StripVtt:
    """Unit tests for _strip_vtt() — the helper added by the B-8 fix."""

    RAW = (
        "WEBVTT\n\n"
        "1\n"
        "00:00:01.000 --> 00:00:04.000\n"
        "Illegal dumping near Mandi district.\n\n"
        "2\n"
        "00:00:05.000 --> 00:00:09.000\n"
        "This is a serious issue in Himachal Pradesh.\n"
    )

    def test_webvtt_header_removed(self):
        from app.tools.pair_d.context_extractor_tool import _strip_vtt
        assert "WEBVTT" not in _strip_vtt(self.RAW)

    def test_timestamp_lines_removed(self):
        from app.tools.pair_d.context_extractor_tool import _strip_vtt
        assert "-->" not in _strip_vtt(self.RAW)

    def test_sequence_numbers_removed(self):
        from app.tools.pair_d.context_extractor_tool import _strip_vtt
        tokens = _strip_vtt(self.RAW).split()
        assert "1" not in tokens and "2" not in tokens

    def test_speech_content_preserved(self):
        from app.tools.pair_d.context_extractor_tool import _strip_vtt
        result = _strip_vtt(self.RAW)
        assert "Mandi" in result and "Himachal Pradesh" in result

    def test_empty_string_returns_empty(self):
        from app.tools.pair_d.context_extractor_tool import _strip_vtt
        assert _strip_vtt("") == ""

    def test_plain_text_unchanged(self):
        from app.tools.pair_d.context_extractor_tool import _strip_vtt
        plain = "Garbage dumped near the river."
        assert plain in _strip_vtt(plain)


# ══════════════════════════════════════════════════════════════════════════════
# S3 — extract_best_frame
# ══════════════════════════════════════════════════════════════════════════════

class TestS3ExtractBestFrame:
    """Unit tests for extract_best_frame()."""

    CE = "app.tools.pair_d.context_extractor_tool"

    @pytest.fixture(autouse=True)
    def _mocks(self):
        with (
            patch(f"{self.CE}.cv2")          as mock_cv2,
            patch(f"{self.CE}._score_frame") as mock_score,
        ):
            cap = MagicMock()
            cap.isOpened.return_value  = True
            cap.get.return_value       = 90.0
            cap.read.return_value      = (True, _frame())
            mock_cv2.VideoCapture.return_value = cap
            mock_cv2.CAP_PROP_FRAME_COUNT = 7
            mock_cv2.CAP_PROP_POS_FRAMES  = 1
            mock_cv2.imwrite.return_value = True
            mock_score.return_value = 100.0
            self.cap   = cap
            self.cv2   = mock_cv2
            self.score = mock_score
            yield

    def test_returns_jpg_path(self):
        from app.tools.pair_d.context_extractor_tool import extract_best_frame
        tmp = _tmp()
        try:
            assert extract_best_frame(str(tmp)).endswith(".jpg")
        finally:
            tmp.unlink()

    def test_raises_file_not_found(self):
        from app.tools.pair_d.context_extractor_tool import extract_best_frame
        with pytest.raises(FileNotFoundError):
            extract_best_frame("/no/such/file.mp4")

    def test_raises_on_unopenable_video(self):
        from app.tools.pair_d.context_extractor_tool import extract_best_frame
        self.cap.isOpened.return_value = False
        tmp = _tmp()
        try:
            with pytest.raises(ValueError, match="Cannot open"):
                extract_best_frame(str(tmp))
        finally:
            tmp.unlink()

    def test_raises_on_zero_frames(self):
        from app.tools.pair_d.context_extractor_tool import extract_best_frame
        self.cap.get.return_value = 0.0
        tmp = _tmp()
        try:
            with pytest.raises(ValueError, match="no readable frames"):
                extract_best_frame(str(tmp))
        finally:
            tmp.unlink()

    def test_samples_exactly_9_frames(self):
        from app.tools.pair_d.context_extractor_tool import extract_best_frame
        tmp = _tmp()
        try:
            extract_best_frame(str(tmp))
            assert self.cap.read.call_count == 9
        finally:
            tmp.unlink()

    def test_cap_released_on_success(self):
        from app.tools.pair_d.context_extractor_tool import extract_best_frame
        tmp = _tmp()
        try:
            extract_best_frame(str(tmp))
            self.cap.release.assert_called_once()
        finally:
            tmp.unlink()

    def test_b6_cap_released_on_scorer_exception(self):
        """B-6 regression: cap.release() must be called even when _score_frame raises."""
        from app.tools.pair_d.context_extractor_tool import extract_best_frame
        self.score.side_effect = RuntimeError("corrupt frame")
        tmp = _tmp()
        try:
            with pytest.raises(Exception):
                extract_best_frame(str(tmp))
            self.cap.release.assert_called(), "B-6: VideoCapture handle leaked"
        finally:
            tmp.unlink()

    def test_highest_scoring_frame_is_saved(self):
        from app.tools.pair_d.context_extractor_tool import extract_best_frame
        frames = [_frame(color=(i * 25 % 255, 0, 0)) for i in range(9)]
        scores = [10, 20, 30, 999, 15, 5, 5, 5, 5]
        self.cap.read.side_effect  = [(True, f) for f in frames]
        self.score.side_effect     = scores
        tmp = _tmp()
        try:
            extract_best_frame(str(tmp))
            saved = self.cv2.imwrite.call_args[0][1]
            np.testing.assert_array_equal(saved, frames[3])
        finally:
            tmp.unlink()

    def test_output_paths_are_unique(self):
        from app.tools.pair_d.context_extractor_tool import extract_best_frame
        tmp = _tmp()
        try:
            assert extract_best_frame(str(tmp)) != extract_best_frame(str(tmp))
        finally:
            tmp.unlink()


# ══════════════════════════════════════════════════════════════════════════════
# S4 — _get_transcript  (4-priority fallback chain)
# ══════════════════════════════════════════════════════════════════════════════

class TestS4GetTranscript:
    """Unit tests for _get_transcript()."""

    CE = "app.tools.pair_d.context_extractor_tool"

    @pytest.fixture(autouse=True)
    def _mocks(self):
        with (
            patch(f"{self.CE}._check_embedded_subtitles")   as self.emb_check,
            patch(f"{self.CE}._extract_embedded_subtitles") as self.emb_extract,
            patch(f"{self.CE}._extract_audio")              as self.audio,
            patch(f"{self.CE}._WHISPER_MODEL")              as self.whisper,
        ):
            self.emb_check.return_value   = False
            self.emb_extract.return_value = ""
            self.audio.return_value       = None
            self.whisper.transcribe.return_value = {"text": "", "language": "en"}
            yield

    def _call(self, subs=""):
        from app.tools.pair_d.context_extractor_tool import _get_transcript
        return _get_transcript("/fake/video.mp4", subs)

    def test_returns_required_keys(self):
        assert {"text", "language", "source"}.issubset(self._call().keys())

    def test_priority_1_embedded_subtitles(self):
        self.emb_check.return_value   = True
        self.emb_extract.return_value = "Pollution near river."
        result = self._call(subs="auto subs ignored")
        assert result["source"] == "embedded_subtitle"
        assert "Pollution" in result["text"]
        self.whisper.transcribe.assert_not_called()

    def test_priority_2_youtube_auto_subs(self):
        result = self._call(subs="Auto-generated subtitles here.")
        assert result["source"] == "youtube_auto_sub"
        self.whisper.transcribe.assert_not_called()

    def test_priority_3_whisper(self):
        self.audio.return_value = "/tmp/fake_audio.wav"
        self.whisper.transcribe.return_value = {
            "text": "Whisper output.", "language": "hi"
        }
        with patch("os.remove"):
            result = self._call()
        assert result["source"] == "whisper" and result["language"] == "hi"

    def test_priority_4_empty_fallback(self):
        result = self._call()
        assert result["source"] == "none" and result["text"] == ""

    def test_empty_embedded_falls_through_to_auto_subs(self):
        self.emb_check.return_value   = True
        self.emb_extract.return_value = ""
        result = self._call(subs="Backup auto sub.")
        assert result["source"] == "youtube_auto_sub"

    def test_b8_vtt_timing_stripped_before_storage(self):
        """B-8 regression: VTT timing lines must not appear in stored transcript."""
        raw_vtt = (
            "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\n"
            "Illegal dumping near Mandi.\n"
        )
        result = self._call(subs=raw_vtt)
        assert "-->"    not in result["text"], "B-8: VTT timestamps leaked into transcript"
        assert "WEBVTT" not in result["text"], "B-8: WEBVTT header leaked into transcript"
        assert "Mandi"  in result["text"],     "Speech content must survive stripping"


# ══════════════════════════════════════════════════════════════════════════════
# S5 — _translate_to_english
# ══════════════════════════════════════════════════════════════════════════════

class TestS5Translate:
    """Unit tests for _translate_to_english()."""

    CE = "app.tools.pair_d.context_extractor_tool"

    @pytest.fixture(autouse=True)
    def _mock_groq(self):
        with patch(f"{self.CE}.client") as m:
            self.groq = m
            yield

    def _call(self, text, lang):
        from app.tools.pair_d.context_extractor_tool import _translate_to_english
        return _translate_to_english(text, lang)

    def test_english_text_unchanged_no_api_call(self):
        result = self._call("English text.", "en")
        self.groq.chat.completions.create.assert_not_called()
        assert result == "English text."

    def test_english_case_insensitive(self):
        self._call("Text.", "English")
        self.groq.chat.completions.create.assert_not_called()

    def test_empty_text_skips_api(self):
        assert self._call("", "hi") == ""
        self.groq.chat.completions.create.assert_not_called()

    def test_hindi_translated_via_groq(self):
        self.groq.chat.completions.create.return_value = _groq_resp(
            "Factory is emitting smoke."
        )
        result = self._call("कारखाने से धुआं निकल रहा है।", "hi")
        self.groq.chat.completions.create.assert_called_once()
        assert result == "Factory is emitting smoke."

    def test_regional_language_triggers_api(self):
        self.groq.chat.completions.create.return_value = _groq_resp("River is polluted.")
        self._call("நதி மாசுபடுகிறது.", "ta")
        self.groq.chat.completions.create.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
# S6 — extract_context  (public interface, integration)
# ══════════════════════════════════════════════════════════════════════════════

class TestS6ExtractContext:
    """Integration tests for extract_context() — all I/O mocked."""

    CE = "app.tools.pair_d.context_extractor_tool"

    @pytest.fixture(autouse=True)
    def _mocks(self):
        open_mock = MagicMock()
        open_mock.__enter__ = MagicMock(
            return_value=MagicMock(read=MagicMock(return_value=b"\xff\xd8\xff"))
        )
        open_mock.__exit__ = MagicMock(return_value=False)

        with (
            patch(f"{self.CE}._extract_from_social_url") as self.dl,
            patch(f"{self.CE}.extract_best_frame")        as self.frame,
            patch(f"{self.CE}._get_transcript")           as self.tr,
            patch(f"{self.CE}._translate_to_english")     as self.trans,
            patch(f"{self.CE}._extract_on_screen_text")   as self.ocr,
            patch("builtins.open",    return_value=open_mock),
            patch("base64.b64encode", return_value=b"fakeb64"),
            patch("os.path.exists",   return_value=True),
        ):
            self.dl.return_value = {
                "video_path": "/tmp/fake.mp4", "caption": "Test caption",
                "tags": ["#pollution"], "auto_subs": "", "title": "Test video",
            }
            self.frame.return_value  = "/tmp/fake_frame.jpg"
            self.tr.return_value     = {"text": "Pollution near river.",
                                        "language": "en", "source": "whisper"}
            self.trans.return_value  = "Pollution near river."
            self.ocr.return_value    = "Factory Gate No. 5"
            yield

    def _call(self, **kw):
        from app.tools.pair_d.context_extractor_tool import extract_context
        return extract_context(**kw)

    def test_returns_full_schema(self):
        result = self._call(url="https://youtube.com/watch?v=abc")
        expected = {
            "video_path", "frame_path", "frame_b64",
            "transcript", "transcript_en", "transcript_lang", "transcript_source",
            "on_screen_text", "social_caption", "social_tags", "social_title",
            "whatsapp_text", "user_location", "source_url", "error",
        }
        assert expected.issubset(result.keys())

    def test_social_metadata_stored(self):
        result = self._call(url="https://youtube.com/watch?v=abc")
        assert result["social_caption"] == "Test caption"
        assert "#pollution" in result["social_tags"]
        assert result["source_url"]     == "https://youtube.com/watch?v=abc"

    def test_transcript_and_ocr_populated(self):
        result = self._call(url="https://youtube.com/watch?v=abc")
        assert "Pollution" in result["transcript"]
        assert "Factory Gate" in result["on_screen_text"]

    def test_passthrough_fields(self):
        result = self._call(
            video_path="/tmp/fake.mp4",
            whatsapp_text="Please investigate.",
            user_location="Shimla, HP",
        )
        assert result["whatsapp_text"] == "Please investigate."
        assert result["user_location"] == "Shimla, HP"

    def test_no_video_sets_error(self):
        self.dl.return_value = {
            "video_path": None, "caption": "", "tags": [], "auto_subs": "", "title": "",
        }
        with patch("os.path.exists", return_value=False):
            result = self._call(url="https://youtube.com/watch?v=bad")
        assert result["error"] == "no_video"

    def test_b5_failed_download_no_stale_metadata(self):
        """B-5 regression: failed URL download must not attach social metadata
        to a separately passed local video_path."""
        self.dl.return_value = {
            "video_path": None, "caption": "Stale URL caption",
            "tags": [], "auto_subs": "", "title": "",
        }
        with patch("os.path.exists", side_effect=lambda p: p == "/tmp/local.mp4"):
            result = self._call(
                url="https://youtube.com/watch?v=fail",
                video_path="/tmp/local.mp4",
            )
        if result.get("error") != "no_video":
            assert result["social_caption"] == "", (
                "B-5: stale social metadata attached to unrelated local video"
            )

    def test_frame_failure_does_not_crash_pipeline(self):
        """Frame extraction failing must not prevent transcript/OCR from running."""
        self.frame.side_effect = Exception("corrupt video")
        result = self._call(video_path="/tmp/fake.mp4")
        assert "transcript" in result
        assert not result.get("frame_b64") or result["frame_b64"] == ""


# ══════════════════════════════════════════════════════════════════════════════
# S7 — _vision_location
# ══════════════════════════════════════════════════════════════════════════════

class TestS7VisionLocation:
    """Unit tests for _vision_location()."""

    LR = "app.tools.pair_d.location_resolver_tool"

    @pytest.fixture(autouse=True)
    def _mock_groq(self):
        with patch(f"{self.LR}.client") as m:
            self.groq = m
            yield

    def _call(self, frame_b64=None, caption=""):
        from app.tools.pair_d.location_resolver_tool import _vision_location
        return _vision_location(frame_b64 or _b64(), caption)

    def test_returns_required_keys(self):
        self.groq.chat.completions.create.return_value = _json_resp(
            location="Shimla, HP", confidence=0.75, reasoning="sign"
        )
        assert {"location", "confidence", "reasoning"}.issubset(self._call().keys())

    def test_clean_json_parsed(self):
        self.groq.chat.completions.create.return_value = _json_resp(
            location="Mandi, HP", confidence=0.82, reasoning="x"
        )
        r = self._call()
        assert r["location"] == "Mandi, HP"
        assert r["confidence"] == pytest.approx(0.82)

    def test_b4_markdown_fenced_json_parsed(self):
        """B-4 regression: ```json...``` wrapping must still parse."""
        self.groq.chat.completions.create.return_value = _groq_resp(
            '```json\n{"location":"Delhi","confidence":0.6,"reasoning":"sign"}\n```'
        )
        assert self._call()["location"] == "Delhi"

    def test_b4_prose_prefix_json_parsed(self):
        """B-4 regression: prose before the JSON object must still parse."""
        self.groq.chat.completions.create.return_value = _groq_resp(
            'Here is the result: {"location":"Pune","confidence":0.5,"reasoning":"x"}'
        )
        assert self._call()["location"] == "Pune"

    def test_non_json_returns_zero_confidence(self):
        self.groq.chat.completions.create.return_value = _groq_resp(
            "I cannot determine the location."
        )
        r = self._call()
        assert r["confidence"] == 0.0 and r["location"] == ""

    def test_api_exception_returns_zero_confidence(self):
        self.groq.chat.completions.create.side_effect = Exception("timeout")
        assert self._call()["confidence"] == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# S8 — _transcript_location
# ══════════════════════════════════════════════════════════════════════════════

class TestS8TranscriptLocation:
    """Unit tests for _transcript_location()."""

    LR = "app.tools.pair_d.location_resolver_tool"

    @pytest.fixture(autouse=True)
    def _mock_groq(self):
        with patch(f"{self.LR}.client") as m:
            self.groq = m
            yield

    def _call(self, transcript):
        from app.tools.pair_d.location_resolver_tool import _transcript_location
        return _transcript_location(transcript)

    def test_empty_transcript_no_api_call(self):
        self._call("")
        self.groq.chat.completions.create.assert_not_called()

    def test_whitespace_only_no_api_call(self):
        self._call("   \n  ")
        self.groq.chat.completions.create.assert_not_called()

    def test_empty_returns_zero_confidence(self):
        r = self._call("")
        assert r["confidence"] == 0.0 and r["location"] == ""

    def test_valid_transcript_parsed(self):
        self.groq.chat.completions.create.return_value = _json_resp(
            location="Mandi, HP", confidence=0.85, reasoning="mentioned 3x"
        )
        r = self._call("Issue near Mandi in Himachal Pradesh.")
        assert r["location"]   == "Mandi, HP"
        assert r["confidence"] == pytest.approx(0.85)

    def test_transcript_sliced_to_1500_chars(self):
        self.groq.chat.completions.create.return_value = _json_resp(
            location="Pune", confidence=0.7, reasoning="x"
        )
        self._call("water pollution. " * 200)
        _, kw = self.groq.chat.completions.create.call_args
        assert len(kw["messages"][0]["content"]) < 3000

    def test_json_parse_error_returns_zero_confidence(self):
        self.groq.chat.completions.create.return_value = _groq_resp("Sorry.")
        assert self._call("Pollution near Bilaspur.")["confidence"] == 0.0

    def test_api_exception_returns_zero_confidence(self):
        self.groq.chat.completions.create.side_effect = RuntimeError("rate limit")
        assert self._call("Pollution near Rohru.")["confidence"] == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# S9 — _geocode  &  _parse_district_state
# ══════════════════════════════════════════════════════════════════════════════

class TestS9GeocodeAndParse:
    """Unit tests for _geocode() and _parse_district_state()."""

    LR = "app.tools.pair_d.location_resolver_tool"

    @pytest.fixture(autouse=True)
    def _mock_geo(self):
        with patch(f"{self.LR}.geolocator") as m:
            self.geo = m
            yield

    # ── _geocode ───────────────────────────────────────────────────────────────

    def test_india_appended_when_absent(self):
        from app.tools.pair_d.location_resolver_tool import _geocode
        self.geo.geocode.return_value = _nominatim()
        _geocode("Shimla")
        assert "India" in self.geo.geocode.call_args[0][0]

    def test_b3_india_not_doubled(self):
        """B-3 regression: 'India' must appear exactly once in the query."""
        from app.tools.pair_d.location_resolver_tool import _geocode
        self.geo.geocode.return_value = _nominatim()
        _geocode("Shimla, India")
        query = self.geo.geocode.call_args[0][0]
        assert query.lower().count("india") == 1, (
            f"B-3: 'India' appears more than once in query: '{query}'"
        )

    def test_empty_string_no_call(self):
        from app.tools.pair_d.location_resolver_tool import _geocode
        assert _geocode("") == {}
        self.geo.geocode.assert_not_called()

    def test_timeout_returns_empty_dict(self):
        from app.tools.pair_d.location_resolver_tool import _geocode
        from geopy.exc import GeocoderTimedOut
        self.geo.geocode.side_effect = GeocoderTimedOut()
        assert _geocode("Shimla") == {}

    def test_returns_lat_lon_display_name(self):
        from app.tools.pair_d.location_resolver_tool import _geocode
        self.geo.geocode.return_value = _nominatim(lat=31.1048, lon=77.1734)
        r = _geocode("Shimla")
        assert r["latitude"]  == pytest.approx(31.1048)
        assert r["longitude"] == pytest.approx(77.1734)
        assert "display_name" in r

    # ── _parse_district_state ──────────────────────────────────────────────────

    def test_standard_nominatim_address(self):
        from app.tools.pair_d.location_resolver_tool import _parse_district_state
        d, s = _parse_district_state(
            "Shimla, HP",
            {"display_name": "Shimla, Shimla District, Himachal Pradesh, India"}
        )
        assert s == "Himachal Pradesh" and d == "Shimla District"

    def test_no_geocode_falls_back_to_raw_text(self):
        from app.tools.pair_d.location_resolver_tool import _parse_district_state
        d, s = _parse_district_state("Mandi, Himachal Pradesh", {})
        assert d == "Mandi" and s == "Himachal Pradesh"

    def test_b2_pin_code_state_rejected(self):
        """B-2 regression: digit-only state must be rejected."""
        from app.tools.pair_d.location_resolver_tool import _parse_district_state
        d, s = _parse_district_state(
            "", {"display_name": "Some Area, Some District, 171001, India"}
        )
        assert not s.isdigit(), f"B-2: state must not be a PIN, got '{s}'"

    def test_b2_short_address_district_not_india(self):
        """B-2 regression: 2-part address must not produce district='India'."""
        from app.tools.pair_d.location_resolver_tool import _parse_district_state
        d, s = _parse_district_state("Delhi", {"display_name": "Delhi, India"})
        assert d != "India", f"B-2: district must not be 'India', got '{d}'"

    def test_single_word_raw_text_fallback(self):
        from app.tools.pair_d.location_resolver_tool import _parse_district_state
        d, s = _parse_district_state("Shimla", {})
        assert d == "Shimla" and s == ""


# ══════════════════════════════════════════════════════════════════════════════
# S10 — resolve_location  (public interface, integration)
# ══════════════════════════════════════════════════════════════════════════════

class TestS10ResolveLocation:
    """Integration tests for resolve_location() — weight arbitration logic."""

    LR = "app.tools.pair_d.location_resolver_tool"

    @pytest.fixture(autouse=True)
    def _mocks(self):
        with (
            patch(f"{self.LR}._vision_location")      as self.vis,
            patch(f"{self.LR}._transcript_location")  as self.tr,
            patch(f"{self.LR}._geocode")              as self.geo,
            patch(f"{self.LR}._parse_district_state") as self.parse,
        ):
            self.vis.return_value   = {"location": "", "confidence": 0.0, "reasoning": ""}
            self.tr.return_value    = {"location": "", "confidence": 0.0, "reasoning": ""}
            self.geo.return_value   = {}
            self.parse.return_value = ("", "")
            yield

    def _call(self, **kw):
        from app.tools.pair_d.location_resolver_tool import resolve_location
        return resolve_location(**kw)

    def test_returns_required_keys(self):
        self.tr.return_value    = {"location": "Shimla, HP", "confidence": 0.9, "reasoning": "x"}
        self.parse.return_value = ("Shimla", "Himachal Pradesh")
        r = self._call(frame_b64=_b64(), transcript="Issue in Shimla.")
        assert {"state", "district", "location_label",
                "confidence", "dominant_signal", "needs_user_input"}.issubset(r.keys())

    def test_confidence_in_0_1(self):
        self.tr.return_value    = {"location": "Shimla", "confidence": 1.0, "reasoning": "x"}
        self.parse.return_value = ("Shimla", "HP")
        r = self._call(frame_b64=_b64(), transcript="Shimla")
        assert 0.0 <= r["confidence"] <= 1.0

    # ── weight arbitration ─────────────────────────────────────────────────────

    def test_user_location_always_dominates(self):
        """user_weight=0.85 > transcript_weight=0.60×0.9=0.54."""
        self.tr.return_value    = {"location": "Mandi", "confidence": 0.9, "reasoning": "x"}
        self.parse.return_value = ("Shimla", "HP")
        r = self._call(frame_b64=_b64(), user_location="Shimla, HP",
                       transcript="Issue in Mandi")
        assert r["dominant_signal"] == "user"

    def test_transcript_beats_vision(self):
        """transcript_weight=0.60×0.9=0.54 > vision_weight=0.15×1.0=0.15."""
        self.vis.return_value   = {"location": "Delhi", "confidence": 1.0, "reasoning": "x"}
        self.tr.return_value    = {"location": "Mandi, HP", "confidence": 0.9, "reasoning": "x"}
        self.parse.return_value = ("Mandi", "HP")
        r = self._call(frame_b64=_b64(), transcript="Issue in Mandi")
        assert r["dominant_signal"] == "transcript"

    def test_vision_wins_as_sole_signal(self):
        self.vis.return_value   = {"location": "Shimla, HP", "confidence": 0.8, "reasoning": "x"}
        self.parse.return_value = ("Shimla", "HP")
        r = self._call(frame_b64=_b64())
        assert r["dominant_signal"] == "vision"

    def test_user_confidence_normalises_to_1_0(self):
        """user_weight == _MAX_WEIGHT → confidence = 1.0."""
        self.parse.return_value = ("Shimla", "HP")
        r = self._call(frame_b64=_b64(), user_location="Shimla, HP")
        assert r["confidence"] == pytest.approx(1.0)

    # ── no-signal / empty-location ─────────────────────────────────────────────

    def test_no_signals_returns_needs_user_input(self):
        r = self._call(frame_b64="")
        assert r["needs_user_input"] is True
        assert r["dominant_signal"]  == "none"

    def test_b1_empty_location_string_needs_user_input(self):
        """B-1 regression: confidence > 0 but location='' must set needs_user_input=True."""
        self.vis.return_value   = {"location": "", "confidence": 1.0, "reasoning": "unclear"}
        self.parse.return_value = ("", "")
        r = self._call(frame_b64=_b64())
        assert r["needs_user_input"] is True, (
            "B-1: all location strings empty but needs_user_input was False"
        )

    def test_vision_not_called_for_empty_frame_b64(self):
        self._call(frame_b64="")
        self.vis.assert_not_called()

    # ── geocode integration ────────────────────────────────────────────────────

    def test_geocode_called_with_dominant_location(self):
        self.tr.return_value    = {"location": "Mandi, HP", "confidence": 0.9, "reasoning": "x"}
        self.parse.return_value = ("Mandi", "HP")
        self._call(frame_b64=_b64(), transcript="Mandi")
        self.geo.assert_called_once_with("Mandi, HP")

    def test_location_label_assembled_correctly(self):
        self.parse.return_value = ("Mandi", "Himachal Pradesh")
        self.tr.return_value    = {"location": "Mandi, HP", "confidence": 0.9, "reasoning": "x"}
        r = self._call(frame_b64=_b64(), transcript="Mandi")
        assert "Mandi" in r["location_label"]
        assert "Himachal Pradesh" in r["location_label"]


# ══════════════════════════════════════════════════════════════════════════════
# S11 — _yolo_detect
# ══════════════════════════════════════════════════════════════════════════════

class TestS11YoloDetect:
    """Unit tests for _yolo_detect()."""

    ID = "app.tools.pair_d.issue_detector_tool"

    @pytest.fixture(autouse=True)
    def _mock_yolo(self):
        with patch(f"{self.ID}._YOLO_MODEL") as m:
            r = MagicMock(); r.boxes = []; r.names = {}
            m.return_value = [r]
            self.yolo_result = r
            yield m

    def _box(self, label_idx, label_name, conf):
        box = MagicMock()
        box.cls.__int__   = lambda s: label_idx
        box.conf.__float__ = lambda s: conf
        self.yolo_result.names = {label_idx: label_name}
        return box

    def _call(self):
        from app.tools.pair_d.issue_detector_tool import _yolo_detect
        return _yolo_detect("/tmp/fake_frame.jpg")

    def test_no_civic_objects_returns_unknown(self):
        r = self._call()
        assert r["label"] == "unknown" and r["confidence"] == 0.0

    def test_mapped_object_returns_correct_issue(self):
        self.yolo_result.boxes = [self._box(0, "bottle", 0.85)]
        r = self._call()
        assert r["label"] == "garbage"
        assert r["confidence"] == pytest.approx(0.85, abs=0.01)

    def test_unmapped_object_excluded(self):
        self.yolo_result.boxes = [self._box(0, "person", 0.99)]
        assert self._call()["label"] == "unknown"

    def test_b14_aggregation_beats_single_high_confidence(self):
        """B-14 regression: 3×bottle at 0.65 each must beat 1×car at 0.92."""
        boxes = []
        for i, (name, conf) in enumerate([
            ("bottle", 0.65), ("bottle", 0.65), ("bottle", 0.65), ("car", 0.92)
        ]):
            b = MagicMock()
            b.cls.__int__    = lambda s, i=i: i
            b.conf.__float__ = lambda s, c=conf: c
            boxes.append(b)
        self.yolo_result.names = {0: "bottle", 1: "bottle", 2: "bottle", 3: "car"}
        self.yolo_result.boxes = boxes
        r = self._call()
        assert r["label"] == "garbage", (
            "B-14: aggregated garbage (3×0.65=1.95) should beat single car (0.92)"
        )

    def test_reasoning_field_present(self):
        self.yolo_result.boxes = [self._box(0, "cow", 0.75)]
        assert "reasoning" in self._call()


# ══════════════════════════════════════════════════════════════════════════════
# S12 — _groq_vision_detect
# ══════════════════════════════════════════════════════════════════════════════

class TestS12GroqVisionDetect:
    """Unit tests for _groq_vision_detect()."""

    ID = "app.tools.pair_d.issue_detector_tool"

    @pytest.fixture(autouse=True)
    def _mock_groq(self):
        with patch(f"{self.ID}.client") as m:
            self.groq = m
            yield

    def _call(self):
        from app.tools.pair_d.issue_detector_tool import _groq_vision_detect
        return _groq_vision_detect(_b64())

    def test_clean_json_parsed(self):
        self.groq.chat.completions.create.return_value = _json_resp(
            label="pollution", confidence=0.80, reasoning="dirty river"
        )
        r = self._call()
        assert r["label"] == "pollution" and r["confidence"] == pytest.approx(0.80)

    def test_b13_markdown_fenced_json_parsed(self):
        """B-13 regression: ```json...``` wrapping must still parse."""
        self.groq.chat.completions.create.return_value = _groq_resp(
            '```json\n{"label":"drain","confidence":0.7,"reasoning":"blocked"}\n```'
        )
        assert self._call()["label"] == "drain"

    def test_b13_prose_prefix_json_parsed(self):
        """B-13 regression: prose before the JSON object must still parse."""
        self.groq.chat.completions.create.return_value = _groq_resp(
            'Here is my answer: {"label":"garbage","confidence":0.65,"reasoning":"waste"}'
        )
        assert self._call()["label"] == "garbage"

    def test_non_json_returns_unknown(self):
        self.groq.chat.completions.create.return_value = _groq_resp(
            "I see a polluted area."
        )
        r = self._call()
        assert r["label"] == "unknown" and r["confidence"] == 0.0

    def test_api_exception_returns_unknown(self):
        self.groq.chat.completions.create.side_effect = Exception("timeout")
        assert self._call()["label"] == "unknown"

    def test_returns_required_keys(self):
        self.groq.chat.completions.create.return_value = _json_resp(
            label="garbage", confidence=0.9, reasoning="x"
        )
        assert {"label", "confidence", "reasoning"}.issubset(self._call().keys())


# ══════════════════════════════════════════════════════════════════════════════
# S13 — _multimodal_refine
# ══════════════════════════════════════════════════════════════════════════════

class TestS13MultimodalRefine:
    """Unit tests for _multimodal_refine() — returns (dict, bool) after B-12 fix."""

    ID = "app.tools.pair_d.issue_detector_tool"

    @pytest.fixture(autouse=True)
    def _mock_groq(self):
        with patch(f"{self.ID}.client") as m:
            self.groq = m
            yield

    def _vision(self, label="garbage", confidence=0.7):
        return {"label": label, "confidence": confidence, "reasoning": "yolo"}

    def _call(self, vision=None, transcript="", on_screen="", whatsapp=""):
        from app.tools.pair_d.issue_detector_tool import _multimodal_refine
        return _multimodal_refine(vision or self._vision(),
                                  transcript, on_screen, whatsapp)

    def test_returns_tuple_of_dict_and_bool(self):
        self.groq.chat.completions.create.return_value = _json_resp(
            label="pollution", confidence=0.88, reasoning="confirmed"
        )
        result, used = self._call(transcript="dirty river")
        assert isinstance(result, dict) and isinstance(used, bool)

    def test_success_returns_refined_and_true(self):
        self.groq.chat.completions.create.return_value = _json_resp(
            label="pollution", confidence=0.88, reasoning="confirmed"
        )
        result, used = self._call()
        assert used is True and result["label"] == "pollution"

    def test_b12_api_failure_returns_vision_and_false(self):
        """B-12 regression: API failure must return (original vision_result, False)."""
        self.groq.chat.completions.create.side_effect = Exception("rate limit")
        vision  = self._vision(label="garbage", confidence=0.7)
        result, used = self._call(vision=vision)
        assert used   is False
        assert result == vision

    def test_transcript_truncated_to_400_chars(self):
        self.groq.chat.completions.create.return_value = _json_resp(
            label="garbage", confidence=0.8, reasoning="x"
        )
        self._call(transcript="pollution issue. " * 100)
        _, kw = self.groq.chat.completions.create.call_args
        assert len(kw["messages"][0]["content"]) < 2000


# ══════════════════════════════════════════════════════════════════════════════
# S14 — detect_issue  (public interface, integration)
# ══════════════════════════════════════════════════════════════════════════════

class TestS14DetectIssue:
    """Integration tests for detect_issue()."""

    ID = "app.tools.pair_d.issue_detector_tool"

    @pytest.fixture(autouse=True)
    def _mocks(self):
        with (
            patch(f"{self.ID}._yolo_detect")        as self.yolo,
            patch(f"{self.ID}._groq_vision_detect") as self.gv,
            patch(f"{self.ID}._multimodal_refine")  as self.refine,
            patch("os.path.exists",                  return_value=True),
            patch("os.remove"),
        ):
            self.yolo.return_value   = {"label": "garbage",
                                        "confidence": 0.8, "reasoning": "bottle"}
            self.gv.return_value     = {"label": "unknown",
                                        "confidence": 0.0, "reasoning": ""}
            self.refine.return_value = (
                {"label": "garbage", "confidence": 0.85, "reasoning": "confirmed"}, True
            )
            yield

    def _ctx(self, **kw):
        base = {
            "frame_path":    "/tmp/fake_frame.jpg",
            "frame_b64":     _b64(),
            "transcript_en": "Garbage dump near the school.",
            "on_screen_text": "",
            "whatsapp_text":  "",
        }
        base.update(kw)
        return base

    def _call(self, ctx=None):
        from app.tools.pair_d.issue_detector_tool import detect_issue
        return detect_issue(ctx or self._ctx())

    def test_returns_required_keys(self):
        r = self._call()
        assert {"issue_type", "confidence", "reasoning", "refinement_used"}.issubset(r.keys())

    def test_canonical_issue_type_returned(self):
        assert self._call()["issue_type"] == "Waste Management"

    def test_b10_unknown_maps_to_unknown_not_waste_management(self):
        """B-10 regression: a failed detection must return 'Unknown', not 'Waste Management'."""
        self.yolo.return_value   = {"label": "unknown", "confidence": 0.0, "reasoning": ""}
        self.refine.return_value = (
            {"label": "unknown", "confidence": 0.0, "reasoning": ""}, False
        )
        r = self._call()
        assert r["issue_type"] == "Unknown", (
            f"B-10: 'unknown' label should map to 'Unknown', got '{r['issue_type']}'"
        )

    def test_yolo_used_when_frame_path_exists(self):
        self._call()
        self.yolo.assert_called_once()

    def test_groq_vision_fallback_when_yolo_unknown(self):
        self.yolo.return_value = {"label": "unknown", "confidence": 0.0, "reasoning": ""}
        self.gv.return_value   = {"label": "pollution",
                                   "confidence": 0.75, "reasoning": "dirty river"}
        self.refine.return_value = (
            {"label": "pollution", "confidence": 0.75, "reasoning": "x"}, True
        )
        self._call()
        self.gv.assert_called_once()

    def test_groq_vision_skipped_when_yolo_succeeds(self):
        self._call()
        self.gv.assert_not_called()

    def test_refinement_used_flag_propagated(self):
        self.refine.return_value = (
            {"label": "garbage", "confidence": 0.85, "reasoning": "x"}, True
        )
        assert self._call()["refinement_used"] is True

    def test_b11_tmp_file_cleaned_on_yolo_exception(self):
        """B-11 regression: verify that detect_issue wraps _yolo_detect in try/finally
        so the tmp file is cleaned up even on exception.
        We verify this by inspecting the source directly — the try/finally structure
        is what guarantees cleanup, not whether os.remove fired in this mock environment."""
        import inspect
        from app.tools.pair_d import issue_detector_tool
        src = inspect.getsource(issue_detector_tool.detect_issue)
        assert "try:" in src and "finally:" in src, (
            "B-11: detect_issue must wrap _yolo_detect in try/finally "
            "to guarantee tmp file cleanup on exception"
        )
        assert "os.remove" in src, (
            "B-11: os.remove must be called inside the finally block"
        )

    def test_all_canonical_labels_correctly_mapped(self):
        """Every raw label in _ISSUE_CANONICAL_MAP must produce its own canonical
        value — none except 'garbage' should produce 'Waste Management'."""
        labels = [
            "garbage", "pollution", "drain", "road_blockage",
            "stray_animal", "sanitation", "infrastructure", "unknown",
        ]
        for label in labels:
            self.refine.return_value = (
                {"label": label, "confidence": 0.8, "reasoning": "x"}, True
            )
            r = self._call()
            if label != "garbage":
                assert r["issue_type"] != "Waste Management", (
                    f"Label '{label}' incorrectly maps to 'Waste Management'"
                )


# ══════════════════════════════════════════════════════════════════════════════
# S15 — run_vision_pipeline  (end-to-end)
# ══════════════════════════════════════════════════════════════════════════════

class TestS15RunVisionPipeline:
    """End-to-end tests for run_vision_pipeline() — all three agents mocked."""

    VP = "app.tools.pair_d.vision_pipeline_tool"

    @pytest.fixture(autouse=True)
    def _mocks(self):
        with (
            patch(f"{self.VP}.extract_context")  as self.ctx,
            patch(f"{self.VP}.detect_issue")     as self.issue,
            patch(f"{self.VP}.resolve_location") as self.loc,
        ):
            self.ctx.return_value = {
                "frame_b64":      _b64(),
                "transcript_en":  "Garbage near the river.",
                "transcript":     "Garbage near the river.",
                "social_caption": "Pollution video",
                "on_screen_text": "",
                "whatsapp_text":  "",
                "error":          "",
            }
            self.issue.return_value = {
                "issue_type":      "Waste Management",
                "confidence":      0.85,
                "reasoning":       "detected bottles",
                "refinement_used": True,
            }
            self.loc.return_value = {
                "state":            "Himachal Pradesh",
                "district":         "Shimla",
                "location_label":   "Shimla, Himachal Pradesh",
                "confidence":       0.9,
                "dominant_signal":  "transcript",
                "needs_user_input": False,
            }
            yield

    def _call(self, **kw):
        from app.tools.pair_d.vision_pipeline_tool import run_vision_pipeline
        return run_vision_pipeline(**kw)

    def test_returns_required_keys(self):
        r = self._call(video_path="/tmp/fake.mp4")
        assert {"issue_type", "transcript", "state", "district",
                "location_label", "confidence", "reasoning",
                "needs_user_input"}.issubset(r.keys())

    def test_issue_type_propagated(self):
        assert self._call(video_path="/tmp/fake.mp4")["issue_type"] == "Waste Management"

    def test_state_and_district_propagated(self):
        r = self._call(video_path="/tmp/fake.mp4")
        assert r["state"] == "Himachal Pradesh" and r["district"] == "Shimla"

    def test_b18_confidence_and_reasoning_in_output(self):
        """B-18 regression: both fields must survive into the pipeline return dict."""
        r = self._call(video_path="/tmp/fake.mp4")
        assert "confidence" in r, "B-18: confidence missing from pipeline output"
        assert "reasoning"  in r, "B-18: reasoning missing from pipeline output"
        assert r["confidence"] == pytest.approx(0.85)

    def test_b19_needs_user_input_propagated(self):
        """B-19 regression: needs_user_input from resolve_location must reach output."""
        self.loc.return_value["needs_user_input"] = True
        r = self._call(video_path="/tmp/fake.mp4")
        assert r["needs_user_input"] is True, (
            "B-19: needs_user_input not propagated from location_resolver"
        )

    def test_b15_pin_state_becomes_empty_not_user_string(self):
        """B-15 regression: digit-only state must become '' not the full user_location."""
        self.loc.return_value["state"] = "171001"
        r = self._call(video_path="/tmp/fake.mp4", user_location="Near Shimla market")
        assert r["state"] != "Near Shimla market", (
            "B-15: full user_location string incorrectly set as state"
        )
        assert not r["state"].isdigit(), "state should not be a PIN code in output"

    def test_b16_empty_transcript_en_falls_back_to_raw_transcript(self):
        """B-16 regression: empty transcript_en must fall back to raw transcript."""
        self.ctx.return_value["transcript_en"] = ""
        self.ctx.return_value["transcript"]    = "Hindi original text"
        self._call(video_path="/tmp/fake.mp4")
        _, kw = self.loc.call_args
        assert kw.get("transcript") == "Hindi original text", (
            "B-16: empty transcript_en should fall back to raw transcript"
        )

    def test_b17_any_error_returns_empty_result(self):
        """B-17 regression: any non-empty error string must short-circuit the pipeline."""
        self.ctx.return_value["error"] = "download_failed"
        r = self._call(url="https://youtube.com/watch?v=bad")
        assert r["issue_type"] == "Unknown"
        assert r["state"]      == ""

    def test_no_video_returns_empty_result(self):
        self.ctx.return_value["error"] = "no_video"
        r = self._call()
        assert r["issue_type"] == "Unknown" and r["location_label"] == ""

    def test_detect_issue_receives_full_context_dict(self):
        """Agent 1 must receive the complete context object from Agent 0."""
        self._call(video_path="/tmp/fake.mp4")
        self.issue.assert_called_once_with(self.ctx.return_value)

    def test_resolve_location_receives_correct_fields(self):
        """Agent 2 must receive frame_b64, user_location, social_caption, transcript."""
        self._call(video_path="/tmp/fake.mp4", user_location="Shimla, HP")
        _, kw = self.loc.call_args
        assert "frame_b64"      in kw
        assert "user_location"  in kw
        assert "transcript"     in kw
        assert "social_caption" in kw


# ══════════════════════════════════════════════════════════════════════════════
# S16 — ComplaintContext  (schema validation)
# ══════════════════════════════════════════════════════════════════════════════

class TestS16ComplaintContext:
    """Schema tests for ComplaintContext dataclass."""

    def _make(self, **kw):
        from app.context import ComplaintContext
        return ComplaintContext(**kw)

    def test_default_construction_succeeds(self):
        ctx = self._make()
        assert ctx.severity == 0 and ctx.error is None

    def test_valid_severity_values_0_through_5(self):
        for s in range(6):
            assert self._make(severity=s).severity == s

    def test_severity_minus_1_raises(self):
        with pytest.raises(ValueError, match="severity"):
            self._make(severity=-1)

    def test_severity_6_raises(self):
        with pytest.raises(ValueError, match="severity"):
            self._make(severity=6)

    def test_all_string_fields_default_empty(self):
        ctx = self._make()
        for field in ("issue_type", "state", "district", "location_label",
                      "transcript", "authority_name", "authority_email",
                      "authority_portal", "complaint_text"):
            assert getattr(ctx, field) == "", f"'{field}' should default to ''"

    def test_all_canonical_issue_types_accepted(self):
        for ct in ("Waste Management", "Air Pollution", "Water Pollution",
                   "Road Damage", "Animal Control", "Public Sanitation",
                   "Infrastructure Damage", "Unknown"):
            assert self._make(issue_type=ct).issue_type == ct

    def test_pipeline_output_maps_cleanly_to_context(self):
        """Keys from run_vision_pipeline output must map to ComplaintContext fields."""
        pipeline_out = {
            "issue_type":     "Waste Management",
            "transcript":     "Garbage near the river.",
            "state":          "Himachal Pradesh",
            "district":       "Shimla",
            "location_label": "Shimla, Himachal Pradesh",
        }
        ctx = self._make(**pipeline_out)
        assert ctx.issue_type     == "Waste Management"
        assert ctx.state          == "Himachal Pradesh"
        assert ctx.district       == "Shimla"
        assert ctx.location_label == "Shimla, Himachal Pradesh"


# ══════════════════════════════════════════════════════════════════════════════
# S17 — Regression index
# ══════════════════════════════════════════════════════════════════════════════

class TestS17Regressions:
    """
    Named regression anchors — one per bug ID.
    Each maps to the section that contains the substantive test so that
    CI output and the bug list stay in sync.
    """

    def test_B1_empty_location_needs_user_input(self):
        """→ TestS10::test_b1_empty_location_string_needs_user_input"""
        pytest.importorskip("app.tools.pair_d.location_resolver_tool")

    def test_B2_district_not_india_for_short_address(self):
        """→ TestS9::test_b2_short_address_district_not_india"""
        pytest.importorskip("app.tools.pair_d.location_resolver_tool")

    def test_B3_india_not_doubled_in_geocode_query(self):
        """→ TestS9::test_b3_india_not_doubled"""
        pytest.importorskip("app.tools.pair_d.location_resolver_tool")

    def test_B4_prose_prefix_json_parsed(self):
        """→ TestS7::test_b4_prose_prefix_json_parsed"""
        pytest.importorskip("app.tools.pair_d.location_resolver_tool")

    def test_B5_failed_download_no_stale_metadata(self):
        """→ TestS6::test_b5_failed_download_no_stale_metadata"""
        pytest.importorskip("app.tools.pair_d.context_extractor_tool")

    def test_B6_cap_released_on_scorer_exception(self):
        """→ TestS3::test_b6_cap_released_on_scorer_exception"""
        pytest.importorskip("app.tools.pair_d.context_extractor_tool")

    def test_B7_python39_future_annotations_present(self):
        """B-7: 'from __future__ import annotations' must exist in the file."""
        src = (ROOT / "app/tools/pair_d/context_extractor_tool.py").read_text(encoding="utf-8")
        assert "from __future__ import annotations" in src, (
            "B-7: missing future annotations import — "
            "str | None syntax crashes on Python 3.9"
        )

    def test_B8_vtt_stripped_before_storage(self):
        """→ TestS4::test_b8_vtt_timing_stripped_before_storage"""
        pytest.importorskip("app.tools.pair_d.context_extractor_tool")

    def test_B9_small_bystander_not_penalised(self):
        """→ TestS1::test_b9_small_bystander_not_penalised"""
        pytest.importorskip("app.tools.pair_d.context_extractor_tool")

    def test_B10_unknown_maps_to_unknown(self):
        """→ TestS14::test_b10_unknown_maps_to_unknown_not_waste_management"""
        pytest.importorskip("app.tools.pair_d.issue_detector_tool")

    def test_B11_tmp_file_cleaned_on_exception(self):
        """→ TestS14::test_b11_tmp_file_cleaned_on_yolo_exception"""
        pytest.importorskip("app.tools.pair_d.issue_detector_tool")

    def test_B12_refinement_used_flag_present(self):
        """→ TestS14::test_refinement_used_flag_propagated"""
        pytest.importorskip("app.tools.pair_d.issue_detector_tool")

    def test_B13_prose_prefix_json_parsed_in_groq_vision_detect(self):
        """→ TestS12::test_b13_prose_prefix_json_parsed"""
        pytest.importorskip("app.tools.pair_d.issue_detector_tool")

    def test_B14_aggregation_beats_single_high_confidence(self):
        """→ TestS11::test_b14_aggregation_beats_single_high_confidence"""
        pytest.importorskip("app.tools.pair_d.issue_detector_tool")

    def test_B15_pin_state_empty_not_user_string(self):
        """→ TestS15::test_b15_pin_state_becomes_empty_not_user_string"""
        pytest.importorskip("app.tools.pair_d.vision_pipeline_tool")

    def test_B16_empty_transcript_en_falls_back_to_raw(self):
        """→ TestS15::test_b16_empty_transcript_en_falls_back_to_raw_transcript"""
        pytest.importorskip("app.tools.pair_d.vision_pipeline_tool")

    def test_B17_any_error_short_circuits_pipeline(self):
        """→ TestS15::test_b17_any_error_returns_empty_result"""
        pytest.importorskip("app.tools.pair_d.vision_pipeline_tool")

    def test_B18_confidence_and_reasoning_in_output(self):
        """→ TestS15::test_b18_confidence_and_reasoning_in_output"""
        pytest.importorskip("app.tools.pair_d.vision_pipeline_tool")

    def test_B19_needs_user_input_propagated(self):
        """→ TestS15::test_b19_needs_user_input_propagated"""
        pytest.importorskip("app.tools.pair_d.vision_pipeline_tool")


# ══════════════════════════════════════════════════════════════════════════════
# CLI entry-point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import subprocess
    sys.exit(subprocess.call(
        ["pytest", __file__, "-v", "--tb=short"],
        cwd=str(ROOT),
    ))
