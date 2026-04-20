# CivicWatch — Scripts: Testing Guide

This document explains every test script in the `scripts/` directory: what it tests, how to set it up, and how to run it. All scripts are run from the **project root** unless stated otherwise.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [test\_direct\_submission.py](#1-test_direct_submissionpy)
3. [test\_e2e.py](#2-test_e2epy)
4. [test\_pair\_d\_vision\_real.py](#3-test_pair_d_vision_realpy)
5. [test\_pair\_d\_vision.py](#4-test_pair_d_visionpy)
6. [test\_trio\_c.py](#5-test_trio_cpy)

---

## Prerequisites

Install the base Python dependencies before running any script:

```bash
pip install httpx rich pytest numpy pillow python-dotenv groq sentence-transformers
```

Make sure your `.env` file at the project root contains:

```
GROQ_API_KEY=your_key_here
```

The following must also be in place before running any backend-dependent test:

- `configs/authority_data.json` — authority routing data
- `data/environmental_laws.txt` — legal corpus for RAG
- YOLO weights (`yolov8n.pt`) and Whisper medium model downloaded

---

## 1. `test_direct_submission.py`

### What it tests

A sequential, five-step integration test against the live backend:

| Step | Endpoint | Assertion |
|------|----------|-----------|
| 1 | `POST /api/process` | Upload a dummy video, receive a tracking ID |
| 2 | `GET /api/status/:id` | Complaint row exists immediately after upload |
| 3 | Polling loop | Pipeline progresses to a terminal state (`completed`, `submitted`, `email_only`) |
| 4 | `GET /api/complaint/:id` | Final DB record has all required fields populated |
| 5 | `POST /api/confirm-location` | Location update is persisted correctly |

If no real video file is found at `scripts/test_assets/sample.mp4`, the script auto-generates a minimal dummy MP4 to exercise the API surface (transcription will be empty, but all routing and DB logic is tested).

### Setup — three terminals

**Terminal 1 — Frontend (only needed for full system context; run once):**
```bash
cd frontend
npm install        # only run once
npx expo start
```

**Terminal 2 — Backend:**
```bash
pip install httpx rich        # only run once
uvicorn app.main:app --reload --port 8000 --host 0.0.0.0
```

**Terminal 3 — Health check, then run the test:**
```bash
curl http://localhost:8000/api/health
python scripts/test_direct_submission.py
```

### What to expect

The script prints colour-coded pass/fail output for each step using `rich`. A clean run ends with:

```
─────────────────── All tests passed ───────────────────
```

---

## 2. `test_e2e.py`

### What it tests

A full async end-to-end test that drives the entire complaint pipeline from video submission through to dispatch confirmation:

| Step | What happens |
|------|--------------|
| 1 | Submit a complaint with a real video file |
| 2 | Poll `/api/status` until terminal or `needs_location` |
| 3 | If `needs_location`, confirm location and resume polling |
| 4 | Assert terminal status is `submitted` or `email_only` |
| 5 | Fetch `/api/complaint/:id` and verify all AI-populated fields |
| 6 | Check mock dispatch logs (`logs/email_mock_log.jsonl`, `logs/whatsapp_mock_log.jsonl`) |

### Setup — same three terminals as above

```bash
# Terminal 2
uvicorn app.main:app --reload --port 8000 --host 0.0.0.0

# Terminal 3 — health check
curl http://localhost:8000/api/health
```

### Running

Two video scenarios are supported, selected via a command-line argument:

```bash
# Default: stray animals video
python scripts/test_e2e.py

# Air pollution / smoke video
python scripts/test_e2e.py pollution
```

Internally the script maps these keys to video files under `data/test_vision/videos/` and sets the complaint description accordingly. The default timeout is **5 minutes** — the full AI pipeline (Whisper + YOLO + Groq + portal navigator) can take a while.

### What to expect

Status updates are printed every 3 seconds as the pipeline progresses:

```
[E2E] Step 2 — Polling status...
  [  3s] detecting_issue
  [  6s] mapping_authority
  [  9s] drafting_complaint
  [ 12s] submitting
  [ 15s] submitted
```

The run ends with `[E2E] ALL CHECKS PASSED.`

---

## 3. `test_pair_d_vision_real.py`

### What it tests

Real-data integration tests for all four perception agents in `app/tools/pair_d/`. Unlike the mocked suite, every test calls **actual** external dependencies:

| Section | Covers |
|---------|--------|
| R1 | `extract_best_frame()` on real video files |
| R2 | Sharpness scoring (`_sharpness`, `_score_frame`) with real cv2 and YOLO |
| R3 | `_get_transcript()` with real Whisper — English, Hindi, silent, VTT, SRT, embedded subs |
| R4 | `_strip_vtt()` on the real `sample_auto.vtt` file |
| R5 | `resolve_location()` with real GPS coords → real Nominatim + Groq |
| R6 | GPS EXIF extraction from `geotagged_sample.jpg` |
| R7 | `detect_issue()` on real frames — membership and confidence-floor checks against `vision_expected.json` |
| R8 | `run_vision_pipeline()` end-to-end on real videos (~1–3 min each) |
| R9 | `extract_context()` schema and field completeness |

Tests **skip** (not fail) when a required file or API key is absent.

### Additional requirements

```bash
pip install pytest numpy pillow python-dotenv
# cv2, torch, ultralytics, groq, geopy must be installed and model weights present
```

The following test assets must be populated under `data/test_vision/` (see `data/README.md`):

- `videos/` — `pollution_smoke.mp4`, `garbage_dump.mp4`, `road_pothole.mp4`, `stray_animals.mp4`, etc.
- `audio/` — `english_complaint.wav`, `hindi_complaint.wav`, `silent.wav`
- `subtitles/` — `sample_auto.vtt`, `sample_clean.srt`
- `metadata/` — `location_metadata.json`, `exif_samples.json`
- `sample_frames/` — `geotagged_sample.jpg`
- `expected_outputs/` — `vision_expected.json`, `location_expected.json`, `context_expected.json`

### Running

```bash
# All real-data tests (takes several minutes)
pytest scripts/test_pair_d_vision_real.py -v -s

# One section only
pytest scripts/test_pair_d_vision_real.py -v -s -k "R3"

# Skip slow tests (Whisper, full pipeline)
pytest scripts/test_pair_d_vision_real.py -v -s -k "not R8"

# Both suites together
pytest scripts/test_pair_d_vision.py scripts/test_pair_d_vision_real.py -v
```

### Output verbosity options

```bash
# Short tracebacks, stop after first 5 failures
pytest scripts/test_pair_d_vision_real.py --tb=short -x

# Only show failures, suppress passing tests
pytest scripts/test_pair_d_vision_real.py --tb=short -q

# Summary only, no tracebacks
pytest scripts/test_pair_d_vision_real.py --tb=no -q
```

### Test design notes

- LLM-dependent assertions check **membership** in the canonical issue-type set and a **confidence floor** from the golden file — never exact string matches, since LLM outputs can legitimately vary.
- Tests marked `@pytest.mark.slow` involve Whisper transcription or the full pipeline and may each take 30 seconds to 3 minutes.
- Each test is fully independent — no shared state between test classes.

---

## 4. `test_pair_d_vision.py`

### What it tests

The **mocked** counterpart to `test_pair_d_vision_real.py`. All external I/O (Groq, Nominatim, YOLO, cv2, Whisper, ffmpeg, yt-dlp) is patched at the boundary — no network access or GPU required. Covers:

| Section | Covers |
|---------|--------|
| S1 | `_sharpness` and `_score_frame` — unit tests |
| S2 | `_strip_vtt()` — VTT header/timestamp stripping (B-8 fix) |
| S3 | `extract_best_frame()` — path handling, frame selection, resource cleanup |
| S4 | `_get_transcript()` — four-priority fallback chain |
| S5 | `_translate_to_english()` — language detection and Groq API call logic |
| S6 | `extract_context()` — full schema, social metadata, error handling |
| S7 | `_vision_location()` — JSON parsing, markdown-fenced JSON (B-4 fix) |
| S8 | `_transcript_location()` — empty transcript guards, input slicing |
| S9 | `_geocode()` and `_parse_district_state()` — India deduplication (B-3), PIN rejection (B-2) |
| S10 | `resolve_location()` — weight arbitration across user / transcript / vision signals |
| S11 | `_yolo_detect()` — label aggregation (B-14 fix) |
| S12 | `_groq_vision_detect()` — prose-prefix JSON parsing (B-13 fix) |
| S13 | `_multimodal_refine()` — API-failure fallback (B-12 fix) |
| S14 | `detect_issue()` — canonical label mapping, temp-file cleanup (B-11 fix) |
| S15 | `run_vision_pipeline()` — end-to-end integration with all three agents mocked |
| S16 | `ComplaintContext` — schema validation, severity bounds |
| S17 | Regression index — one named anchor per bug ID (B-1 through B-19) |

### Requirements

```bash
pip install pytest numpy pillow
# cv2, torch, groq, geopy do NOT need to be installed — they are mocked at import time
```

### Running

```bash
# Full suite
pytest scripts/test_pair_d_vision.py -v

# One section only
pytest scripts/test_pair_d_vision.py -v -k "S10"

# All regression tests
pytest scripts/test_pair_d_vision.py -v -k "regression"

# With coverage report
pytest scripts/test_pair_d_vision.py -v --tb=short --cov=app/tools/pair_d
```

### Regression index

Section S17 contains one test stub per bug ID (B-1 → B-19). Each stub simply verifies the relevant module can be imported, while the substantive assertion lives in the named section. This keeps CI output and the bug tracker in sync — a failure in S17 tells you exactly which bug regression to investigate.

---

## 5. `test_trio_c.py`

### What it tests

A standalone Python test runner (no pytest required) for all four reasoning and intelligence agents in `app/tools/trio_c/`:

| Section | Tool | External calls |
|---------|------|----------------|
| 1 | `authority_lookup_tool` | None — pure logic against `configs/authority_data.json` |
| 2 | `smart_rag_tool` | None — local embedding model (`sentence-transformers`) |
| 3 | `severity_score_tool` | Live Groq LLM call |
| 4 | `complaint_draft_tool` | Integration: severity + RAG + lookup + Groq |
| 5 | `ComplaintContext` | None — dataclass validation |

Key things verified:

- **Authority lookup:** correct authority and level for severity 1–5, graceful fallback for unknown keys, case-insensitive matching, correct return shape
- **RAG:** `top_k` respected, results sorted by score descending, semantic relevance of top hit, score in `[0, 1]`
- **Severity scoring:** return shape, severity in `{1, 2, 3, 4}`, minor issues score low, critical issues score high
- **Complaint drafting:** non-empty output, no failure sentinels, word count ≤ 200, no letter-style openers ("Dear Sir" etc.), authority name present, graceful handling of unknown locations and whitespace-padded inputs
- **ComplaintContext:** valid severity range (`0–5`), `ValueError` on out-of-range values, correct defaults, presence of `complaint_ref_id` and `authority_phone` fields

### Requirements

```bash
pip install groq sentence-transformers python-dotenv numpy
```

`GROQ_API_KEY` must be set in `.env` or the environment. Sections 3 and 4 will print a warning and skip if the key is missing.

### Running

```bash
python scripts/test_trio_c.py
```

The script prints colour-coded `[PASS]` / `[FAIL]` lines for each test and ends with a summary table:

```
============================================================
  SUMMARY
============================================================
  [PASS]  [authority_lookup]  severity=1 → level1, correct authority
  [PASS]  [smart_rag]  top_k=3 returns exactly 3 results
  [PASS]  [severity_score]  severity is int in {1,2,3,4}
  ...
  32/32 passed
```

Sections 3 and 4 include `time.sleep(1)` calls between LLM requests to avoid Groq rate limits — this is expected behaviour, not a hang.

---

## Quick Reference

| Script | Runner | Network / GPU needed | Approx. runtime |
|--------|--------|----------------------|-----------------|
| `test_direct_submission.py` | `python` | Backend running locally | ~2 min |
| `test_e2e.py` | `python` | Backend + real videos | ~5 min |
| `test_pair_d_vision_real.py` | `pytest` | Groq API + GPU (YOLO/Whisper) | ~10–20 min |
| `test_pair_d_vision.py` | `pytest` | None (fully mocked) | ~10 sec |
| `test_trio_c.py` | `python` | Groq API | ~2–3 min |