# scripts/test_e2e.py

import asyncio
import httpx

BASE_URL  = "http://localhost:8000/api"

POLL_INTERVAL = 3    # seconds between status polls
POLL_TIMEOUT  = 300  # 5 minutes max for full pipeline


async def run_e2e():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:

        # ── 1. Submit complaint ─────────────────────────────────────────────
        print("\n[E2E] Step 1 — Submitting complaint...")
        with open(VIDEO_PATH, "rb") as f:
            response = await client.post("/process", data={
                "name":                   "Ravi Kumar",
                "email":                  "ravi@test.com",
                "phone":                  "9876543210",
                "state":                  "Himachal Pradesh",
                "district":               "Shimla",
                "landmark":               "Near Mall Road",
                "user_issue_description": "Stray animals on road causing blockage",
                "user_id":                "test-user-001",
            }, files={"video": ("test_video.mp4", f, "video/mp4")})

        assert response.status_code == 200, f"Process failed: {response.text}"
        tracking_id = response.json()["id"]
        print(f"[E2E] Tracking ID: {tracking_id}")

        # ── 2. Poll status until terminal or needs_location ─────────────────
        print("\n[E2E] Step 2 — Polling status...")
        final_status = await _poll_until_terminal(client, tracking_id)

        # ── 3. Handle location confirmation if needed ───────────────────────
        if final_status == "needs_location":
            print("\n[E2E] Step 3 — Confirming location...")
            resp = await client.post("/confirm-location", json={
                "id":            tracking_id,
                "final_state":   "Himachal Pradesh",
                "final_district":"Shimla",
                "final_landmark":"Near Mall Road",
            })
            assert resp.status_code == 200, f"Confirm location failed: {resp.text}"
            print("[E2E] Location confirmed — resuming pipeline poll...")
            final_status = await _poll_until_terminal(client, tracking_id)

        # ── 4. Assert terminal status ───────────────────────────────────────
        print(f"\n[E2E] Final status: {final_status}")
        assert final_status in {"submitted", "email_only"}, \
            f"Expected submitted/email_only, got: {final_status}"

        # ── 5. Fetch full complaint detail and assert fields ────────────────
        print("\n[E2E] Step 5 — Fetching complaint detail...")
        detail = (await client.get(f"/complaint/{tracking_id}")).json()

        print(f"  issue_type:       {detail.get('issue_type')}")
        print(f"  state:            {detail.get('state')}")
        print(f"  district:         {detail.get('district')}")
        print(f"  severity:         {detail.get('severity')}")
        print(f"  authority_name:   {detail.get('authority_name')}")
        print(f"  authority_email:  {detail.get('authority_email')}")
        print(f"  complaint_text:   {detail.get('complaint_text', '')[:80]}...")
        print(f"  complaint_ref_id: {detail.get('complaint_ref_id')}")
        print(f"  submission_status:{detail.get('submission_status')}")

        assert detail.get("issue_type"),      "issue_type is empty"
        assert detail.get("authority_name"),  "authority_name is empty"
        assert detail.get("complaint_text"),  "complaint_text is empty"
        assert detail.get("severity"),        "severity is 0 or missing"

        if final_status == "submitted":
            assert detail.get("complaint_ref_id"), "submitted but no complaint_ref_id"

        # ── 6. Check mock logs ──────────────────────────────────────────────
        print("\n[E2E] Step 6 — Checking mock dispatch logs...")
        _check_mock_log("logs/email_mock_log.jsonl",     tracking_id, "email")
        _check_mock_log("logs/whatsapp_mock_log.jsonl",  tracking_id, "whatsapp")

        print("\n[E2E] ALL CHECKS PASSED.")
        return tracking_id


async def _poll_until_terminal(client, tracking_id: str) -> str:
    """
    Polls /status until a terminal or gate status is reached.
    Terminal:     submitted, email_only, failed
    Gate:         needs_location
    In-progress:  pending, detecting_issue, mapping_authority,
                  drafting_complaint, submitting, authority_mapped
    """
    terminal = {"submitted", "email_only", "failed", "needs_location"}
    elapsed  = 0

    while elapsed < POLL_TIMEOUT:
        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

        resp   = await client.get(f"/status/{tracking_id}")
        status = resp.json().get("status")
        logs   = resp.json().get("logs", [])

        print(f"  [{elapsed:>4}s] {status}")
        if logs:
            print(f"         → {logs[-1]}")   # print latest log line

        if status in terminal:
            return status

    raise TimeoutError(f"Pipeline did not complete within {POLL_TIMEOUT}s")


def _check_mock_log(filepath: str, tracking_id: str, channel: str):
    """Verifies a mock dispatch log entry exists for this tracking_id."""
    import json, os
    if not os.path.exists(filepath):
        print(f"  [{channel}] No log file found — dispatch may have been skipped.")
        return
    with open(filepath) as f:
        entries = [json.loads(line) for line in f if line.strip()]
    match = [e for e in entries if e.get("tracking_id") == tracking_id]
    if match:
        print(f"  [{channel}] Mock log entry found. To: {match[0].get('to')}")
    else:
        print(f"  [{channel}] WARNING: No log entry for {tracking_id}")


if __name__ == "__main__":
    import sys

    video_options = {
        "stray":     ("data/test_vision/videos/stray_animals.mp4",     "Stray animals roaming near residential area causing disturbance"),
        "pollution": ("data/test_vision/videos/pollution_smoke.mp4",    "Heavy smoke and fumes from factory chimney near residential colony"),
    }

    choice = sys.argv[1] if len(sys.argv) > 1 else "stray"
    if choice not in video_options:
        print(f"Unknown option '{choice}'. Choose from: {list(video_options.keys())}")
        sys.exit(1)

    VIDEO_PATH, USER_DESCRIPTION = video_options[choice]
    print(f"[E2E] Running with: {VIDEO_PATH}")
    asyncio.run(run_e2e())