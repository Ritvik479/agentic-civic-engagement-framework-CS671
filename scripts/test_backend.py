"""
scripts/test_backend.py

Tests:
  1. POST /api/process      — upload a dummy video, get tracking ID back
  2. GET  /api/status/:id   — verify complaint row exists in DB immediately
  3. Polling loop           — watch pipeline progress until terminal state
  4. GET  /api/complaint/:id — verify final DB record is fully populated

Usage:
    python scripts/test_backend.py

Requirements:
    pip install httpx rich
"""

import time
import sys
import httpx
from rich.console import Console
from rich.table import Table
from rich import print as rprint

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_URL = "http://localhost:8000/api"
DUMMY_VIDEO_PATH = "scripts/test_assets/sample.mp4"   # see note below
POLL_INTERVAL = 3       # seconds between status checks
POLL_TIMEOUT  = 120     # give up after this many seconds

console = Console()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def ok(msg):   console.print(f"[bold green]  ✓[/bold green] {msg}")
def fail(msg): console.print(f"[bold red]  ✗[/bold red] {msg}"); sys.exit(1)
def info(msg): console.print(f"[bold yellow]  >[/bold yellow] {msg}")


# ---------------------------------------------------------------------------
# Step 1 — POST /api/process
# ---------------------------------------------------------------------------
def test_upload():
    console.rule("[bold]Step 1 — POST /api/process[/bold]")

    # Create a minimal valid MP4 if no real sample exists
    # (just enough bytes to pass the extension + MIME check)
    import os
    os.makedirs("scripts/test_assets", exist_ok=True)
    if not os.path.exists(DUMMY_VIDEO_PATH):
        info("No sample.mp4 found — creating a dummy file (will fail transcription but tests the API surface)")
        with open(DUMMY_VIDEO_PATH, "wb") as f:
            # Minimal ftyp box — recognised as MP4 by most MIME sniffers
            f.write(bytes.fromhex(
                "0000001866747970" "6d703432" "00000000"
                "6d703432" "6d703431" "69736f6d"
            ))

    payload = {
        "name":                   "Test User",
        "email":                  "test@civicwatch.in",
        "phone":                  "9876543210",
        "state":                  "Uttar Pradesh",
        "district":               "Jhansi",
        "landmark":               "Near Collectorate",
        "user_issue_description": "Open drain causing flooding on main road",
    }

    info(f"Sending to {BASE_URL}/process ...")

    try:
        with open(DUMMY_VIDEO_PATH, "rb") as vf:
            response = httpx.post(
                f"{BASE_URL}/process",
                data=payload,
                files={"video": ("sample.mp4", vf, "video/mp4")},
                timeout=60,
            )
    except httpx.ConnectError:
        fail(f"Could not connect to {BASE_URL}. Is the backend running?")

    if response.status_code != 200:
        fail(f"POST /process returned {response.status_code}: {response.text}")

    data = response.json()
    tracking_id = data.get("id")
    status       = data.get("status")

    if not tracking_id:
        fail(f"Response missing 'id' field: {data}")

    ok(f"Tracking ID:  {tracking_id}")
    ok(f"Initial status: {status}")

    return tracking_id


# ---------------------------------------------------------------------------
# Step 2 — GET /api/status immediately (DB row must exist)
# ---------------------------------------------------------------------------
def test_immediate_status(tracking_id):
    console.rule("[bold]Step 2 — GET /api/status (immediate)[/bold]")

    response = httpx.get(f"{BASE_URL}/status/{tracking_id}", timeout=10)

    if response.status_code == 404:
        fail("Complaint row not found immediately after upload — create_pending_complaint() may not be awaited correctly")

    if response.status_code != 200:
        fail(f"GET /status returned {response.status_code}: {response.text}")

    data = response.json()
    ok(f"Status: {data['status']}")
    ok(f"Logs so far: {data.get('logs', [])}")


# ---------------------------------------------------------------------------
# Step 3 — Poll until terminal state
# ---------------------------------------------------------------------------
def test_polling(tracking_id):
    console.rule("[bold]Step 3 — Polling pipeline progress[/bold]")

    TERMINAL = {"completed", "failed"}
    elapsed  = 0
    last_status = None

    while elapsed < POLL_TIMEOUT:
        response = httpx.get(f"{BASE_URL}/status/{tracking_id}", timeout=10)

        if response.status_code != 200:
            fail(f"Polling got {response.status_code}: {response.text}")

        data   = response.json()
        status = data["status"]
        logs   = data.get("logs", [])

        if status != last_status:
            info(f"[{elapsed:>3}s]  Status changed → {status}")
            for log in logs:
                console.print(f"         [dim]{log}[/dim]")
            last_status = status

        if status in TERMINAL:
            if status == "completed":
                ok("Pipeline reached 'completed'")
            else:
                fail("Pipeline reached 'failed' — check backend logs for error details")
            return status

        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

    fail(f"Pipeline did not reach a terminal state within {POLL_TIMEOUT}s")


# ---------------------------------------------------------------------------
# Step 4 — GET /api/complaint/:id (verify full DB record)
# ---------------------------------------------------------------------------
def test_final_record(tracking_id):
    console.rule("[bold]Step 4 — GET /api/complaint (DB record check)[/bold]")

    response = httpx.get(f"{BASE_URL}/complaint/{tracking_id}", timeout=10)

    if response.status_code != 200:
        fail(f"GET /complaint returned {response.status_code}: {response.text}")

    record = response.json()

    # Fields that must be populated after a successful run
    REQUIRED_FIELDS = [
        "tracking_id",
        "submission_status",
        "state",
        "district",
        "name",
        "email",
        "phone",
    ]

    # Fields populated by the AI pipeline — warn if missing but don't fail
    # (dummy video may cause transcription to be empty)
    PIPELINE_FIELDS = [
        "issue_type",
        "transcript",
        "authority_name",
        "authority_email",
        "complaint_text",
    ]

    all_ok = True
    for field in REQUIRED_FIELDS:
        val = record.get(field)
        if val:
            ok(f"{field}: {val}")
        else:
            console.print(f"[bold red]  ✗[/bold red] {field}: MISSING or NULL")
            all_ok = False

    console.print()
    info("Pipeline-populated fields (may be empty with dummy video):")
    for field in PIPELINE_FIELDS:
        val = record.get(field)
        if val:
            ok(f"{field}: {str(val)[:80]}")
        else:
            console.print(f"[dim]    {field}: empty[/dim]")

    # Print full record as a table
    console.print()
    table = Table(title=f"Full DB Record — {tracking_id}", show_lines=True)
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")

    for k, v in record.items():
        table.add_row(k, str(v)[:120] if v is not None else "[dim]NULL[/dim]")

    console.print(table)

    if not all_ok:
        fail("Some required fields are missing from the DB record — see above")

    ok("DB record looks correct")


# ---------------------------------------------------------------------------
# Step 5 — POST /api/confirm-location (optional location update)
# ---------------------------------------------------------------------------
def test_confirm_location(tracking_id):
    console.rule("[bold]Step 5 — POST /api/confirm-location[/bold]")

    payload = {
        "id":             tracking_id,
        "final_state":    "Uttar Pradesh",
        "final_district": "Jhansi",
        "final_landmark": "Near Collectorate",
    }

    response = httpx.post(f"{BASE_URL}/confirm-location", json=payload, timeout=10)

    if response.status_code != 200:
        fail(f"POST /confirm-location returned {response.status_code}: {response.text}")

    data = response.json()
    ok(f"confirm-location status: {data.get('status')}")

    # Verify location was actually persisted
    record = httpx.get(f"{BASE_URL}/complaint/{tracking_id}", timeout=10).json()
    assert record.get("state")    == "Uttar Pradesh", "state not persisted"
    assert record.get("district") == "Jhansi",        "district not persisted"
    assert record.get("landmark") == "Near Collectorate", "landmark not persisted"
    ok("Location correctly persisted to DB")


# ---------------------------------------------------------------------------
# Run all steps
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    console.print()
    console.rule("[bold cyan]CivicWatch Backend Test Suite[/bold cyan]")
    console.print()

    tracking_id = test_upload()
    test_immediate_status(tracking_id)
    final_status = test_polling(tracking_id)

    if final_status == "completed":
        test_final_record(tracking_id)
        test_confirm_location(tracking_id)

    console.print()
    console.rule("[bold green]All tests passed[/bold green]")
    console.print()