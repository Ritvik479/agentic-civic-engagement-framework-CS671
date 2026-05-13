# db/database.py
# ---------------------------------------------------------------------------
# SQLite database layer for the Agentic Civic Complaint System
# Pair B owns this file.
# ---------------------------------------------------------------------------

import aiosqlite
import os
from typing import Optional

from app.schemas.issue_schema import FinalComplaint


# ---------------------------------------------------------------------------
# Database file path
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(__file__), "complaints.db")


# ---------------------------------------------------------------------------
# Initialize database tables
# Called once when FastAPI server starts — use asyncio.run() or a startup event
# ---------------------------------------------------------------------------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                tracking_id TEXT UNIQUE NOT NULL,
                user_id TEXT,

                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

                video_path TEXT,
                video_url TEXT,
                name TEXT,
                email TEXT,
                phone TEXT,
                user_issue_description TEXT,

                issue_type TEXT,

                -- FIX: was a single 'location TEXT' — split into coordinates
                -- + label so confirmed lat/lng from POST /confirm-location
                -- can be stored and used directly by authority mapping
                state TEXT,
                district TEXT,
                location_label TEXT,
                landmark TEXT,

                severity INTEGER,
                transcript TEXT,

                authority_name TEXT,
                authority_email TEXT,
                authority_portal TEXT,
                complaint_text TEXT,
                authority_level     TEXT DEFAULT 'level1',
                authority_level_num INTEGER DEFAULT 1,

                submission_status TEXT DEFAULT 'pending',
                submission_screenshot TEXT,
                complaint_ref_id TEXT,            -- ADD
                authority_phone TEXT,             -- ADD
                authority_code TEXT,              -- ADD

                error TEXT
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS complaint_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tracking_id TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await conn.commit()

    print("[DB] Initialised — complaints.db ready.")


# ---------------------------------------------------------------------------
# Create complaint immediately after upload (before background processing)
# Prevents frontend GET /status/:id from getting 404 during processing
# ---------------------------------------------------------------------------
async def create_pending_complaint(
    tracking_id: str,
    user_id: str,
    video_path: str,
    video_url: str = "",
    name: str = "",
    email: str = "",
    phone: str = "",
    state: str = "",
    district: str = "",
):
    conn = await aiosqlite.connect(DB_PATH)
    try:
        await conn.execute("""
            INSERT INTO complaints (
                tracking_id,
                user_id,
                video_path,
                video_url,
                name,
                email,
                phone,
                state,
                district,
                submission_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (tracking_id, user_id, video_path, video_url, name, email, phone, state, district, "pending"))

        await conn.commit()
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Update complaint processing status
# pending → detecting_issue → mapping_authority → submitted
# ---------------------------------------------------------------------------
async def update_status(tracking_id: str, status: str):
    conn = await aiosqlite.connect(DB_PATH)
    try:
        await conn.execute("""
            UPDATE complaints
            SET submission_status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE tracking_id = ?
        """, (status, tracking_id))

        await conn.commit()
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Update confirmed state/district from POST /confirm-location
# Called by api.py after the user corrects their location on the mobile app.
# Persists location information to the complaints table so authority mapping
# can use them directly — this is the source of truth for location.
# ---------------------------------------------------------------------------
async def update_location(tracking_id: str, state: str, district: str, landmark: str = "", location_label: str = ""):
    if not location_label:
        parts = [p for p in [landmark, district, state] if p]
        location_label = ", ".join(parts)
    conn = await aiosqlite.connect(DB_PATH)
    try:
        await conn.execute("""
            UPDATE complaints
            SET state          = ?,
                district       = ?,
                landmark       = ?,
                location_label = ?,
                updated_at     = CURRENT_TIMESTAMP
            WHERE tracking_id  = ?
        """, (state, district, landmark, location_label, tracking_id))
        await conn.commit()
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Insert one progress log message
# ---------------------------------------------------------------------------
async def insert_log(tracking_id: str, message: str):
    conn = await aiosqlite.connect(DB_PATH)
    try:
        await conn.execute("""
            INSERT INTO complaint_logs (tracking_id, message)
            VALUES (?, ?)
        """, (tracking_id, message))

        await conn.commit()
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Fetch all logs for one complaint (for frontend polling)
# ---------------------------------------------------------------------------
async def fetch_logs(tracking_id: str) -> list[str]:
    conn = await aiosqlite.connect(DB_PATH)
    try:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("""
            SELECT message
            FROM complaint_logs
            WHERE tracking_id = ?
            ORDER BY timestamp ASC
        """, (tracking_id,))

        rows = await cursor.fetchall()
        return [row["message"] for row in rows]
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Update full complaint record from FinalComplaint (pipeline terminal state)
# ---------------------------------------------------------------------------
async def save_complaint_record(tracking_id: str, complaint: FinalComplaint):
    conn = await aiosqlite.connect(DB_PATH)
    try:
        await conn.execute("""
            UPDATE complaints SET
                issue_type              = ?,
                severity                = ?,
                location_label          = ?,
                complaint_text          = ?,
                authority_name          = ?,
                authority_code          = ?,
                authority_portal        = ?,
                authority_email         = ?,
                submission_status       = ?,
                complaint_ref_id        = ?,
                updated_at              = CURRENT_TIMESTAMP
            WHERE tracking_id = ?
        """, (
            complaint.issue_category.value,
            complaint.severity,
            complaint.issue_location,
            complaint.issue_description,
            complaint.authority_name,
            complaint.authority_code,
            complaint.authority_portal,
            complaint.submission_endpoint,
            complaint.status.value,
            complaint.complaint_id or "",
            tracking_id
        ))
        await conn.commit()
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Fetch one complaint by tracking ID
# Returns full complaint dict, or None if not found
# ---------------------------------------------------------------------------
async def fetch_complaint(tracking_id: str) -> Optional[dict]:
    conn = await aiosqlite.connect(DB_PATH)
    try:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("""
            SELECT *
            FROM complaints
            WHERE tracking_id = ?
        """, (tracking_id,))

        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Fetch slim complaint list for dashboard
# ---------------------------------------------------------------------------
async def fetch_slim_complaints(user_id: str = None) -> list[dict]:
    conn = await aiosqlite.connect(DB_PATH)
    try:
        conn.row_factory = aiosqlite.Row

        if user_id:
            cursor = await conn.execute("""
                SELECT
                    tracking_id,
                    submission_status,
                    issue_type,
                    state,
                    district,
                    location_label,
                    severity,
                    created_at
                FROM complaints
                WHERE user_id = ?
                ORDER BY created_at DESC
            """, (user_id,))
        else:
            cursor = await conn.execute("""
                SELECT
                    tracking_id,
                    submission_status,
                    issue_type,
                    state,
                    district,
                    location_label,
                    severity,
                    created_at
                FROM complaints
                ORDER BY created_at DESC
            """)

        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await conn.close()
