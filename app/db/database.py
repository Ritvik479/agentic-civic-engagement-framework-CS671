# db/database.py
# ---------------------------------------------------------------------------
# SQLite database layer for the Agentic Civic Complaint System
# Pair B owns this file.
# ---------------------------------------------------------------------------

import aiosqlite
import os
from typing import Optional

from app.context import ComplaintContext


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
                submission_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (tracking_id, user_id, video_path, video_url, name, email, phone, "pending"))

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
# Insert or update full complaint record
# Safe to call multiple times as pipeline stages complete
# ---------------------------------------------------------------------------
async def save_complaint(ctx: ComplaintContext):
    conn = await aiosqlite.connect(DB_PATH)
    try:
        await conn.execute("""
            INSERT INTO complaints (
                tracking_id, user_id, video_path, video_url,
                name, email, phone, user_issue_description,
                issue_type,
                state, district, landmark, location_label,
                severity, transcript,
                authority_name, authority_email, authority_portal,
                complaint_text, authority_level, authority_level_num,
                submission_status, submission_screenshot,
                complaint_ref_id, authority_phone,
                error
            )
            VALUES (
                :tracking_id, :user_id, :video_path, :video_url,
                :name, :email, :phone, :user_issue_description,
                :issue_type,
                :state, :district, :landmark, :location_label,
                :severity, :transcript,
                :authority_name, :authority_email, :authority_portal,
                :complaint_text, :authority_level, :authority_level_num,
                :submission_status, :submission_screenshot,
                :complaint_ref_id, :authority_phone,
                :error
            )
            ON CONFLICT(tracking_id) DO UPDATE SET
                issue_type              = excluded.issue_type,
                state                   = excluded.state,
                district                = excluded.district,
                landmark                = excluded.landmark,
                location_label          = excluded.location_label,
                severity                = excluded.severity,
                transcript              = excluded.transcript,
                authority_name          = excluded.authority_name,
                authority_email         = excluded.authority_email,
                authority_portal        = excluded.authority_portal,
                complaint_text          = excluded.complaint_text,
                authority_level         = excluded.authority_level,
                authority_level_num     = excluded.authority_level_num,
                submission_status       = excluded.submission_status,
                submission_screenshot   = excluded.submission_screenshot,
                complaint_ref_id        = excluded.complaint_ref_id,
                authority_phone         = excluded.authority_phone,
                user_issue_description  = excluded.user_issue_description,
                error                   = excluded.error,
                updated_at              = CURRENT_TIMESTAMP
        """, {
            "tracking_id":              ctx.tracking_id,
            "user_id":                  ctx.user_id,
            "video_path":               ctx.video_path,
            "video_url":                ctx.video_url,
            "name":                     ctx.name,
            "email":                    ctx.email,
            "phone":                    ctx.phone,
            "user_issue_description":   ctx.user_issue_description,
            "issue_type":               ctx.issue_type,
            "state":                    ctx.state,
            "district":                 ctx.district,
            "landmark":                 ctx.landmark,
            "location_label":           ctx.location_label,
            "severity":                 ctx.severity,
            "transcript":               ctx.transcript,
            "authority_name":           ctx.authority_name,
            "authority_email":          ctx.authority_email,
            "authority_portal":         ctx.authority_portal,
            "complaint_text":           ctx.complaint_text,
            "authority_level":          ctx.authority_level,
            "authority_level_num":      ctx.authority_level_num,
            "submission_status":        ctx.submission_status,
            "submission_screenshot":    ctx.submission_screenshot,
            "complaint_ref_id":         ctx.complaint_ref_id,
            "authority_phone":          ctx.authority_phone,
            "error":                    ctx.error,
        })
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
#
# FIX: was using .format() to splice a WHERE clause into the query string.
# That pattern looks like a SQL injection risk and confuses reviewers.
# Replaced with two explicit queries — one for a specific user, one for all.
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