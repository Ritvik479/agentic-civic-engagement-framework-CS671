# db/database.py
# ---------------------------------------------------------------------------
# SQLite database layer for the Agentic Civic Complaint System
#
# Pair B owns this file.
#
# Responsibilities:
# 1. Create database tables on startup
# 2. Insert/update complaint records
# 3. Store progress logs for frontend polling
# 4. Provide complaint fetch APIs for FastAPI routes
#
# This version is upgraded to support:
# - async frontend polling
# - complaint lifecycle tracking
# - log timeline support
# - immediate pending complaint creation
# ---------------------------------------------------------------------------

import sqlite3
import os
from typing import Optional

# FIXED IMPORT:
# Use relative import if database.py is inside app/db/
# Adjust based on your folder structure.
from app.context import ComplaintContext
# If your structure is different, tell me and I'll correct it exactly.


# ---------------------------------------------------------------------------
# Database file path
# complaints.db will live inside db/ folder
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(__file__), "complaints.db")


# ---------------------------------------------------------------------------
# Open SQLite connection
# row_factory lets us access row["column_name"]
# ---------------------------------------------------------------------------
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Initialize database tables
# Called once when FastAPI server starts
# ---------------------------------------------------------------------------
def init_db():
    conn = _connect()

    # -----------------------------------------------------------------------
    # Main complaints table
    # Stores one row per complaint
    # -----------------------------------------------------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            tracking_id TEXT UNIQUE NOT NULL,
            user_id TEXT,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            -- Uploaded video path
            video_path TEXT,

            -- Pair D outputs
            issue_type TEXT,
            location TEXT,
            severity INTEGER,
            transcript TEXT,

            -- Trio C outputs
            authority_name TEXT,
            authority_email TEXT,
            authority_portal TEXT,
            complaint_text TEXT,

            -- Pair B / Pair E status tracking
            submission_status TEXT DEFAULT 'pending',
            submission_screenshot TEXT,

            -- Error tracking
            error TEXT
        )
    """)

    # -----------------------------------------------------------------------
    # Complaint logs table
    # Stores progress timeline for frontend polling
    # Example:
    # "Video uploaded"
    # "Issue detection started"
    # "Authority mapped"
    # -----------------------------------------------------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS complaint_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_id TEXT NOT NULL,
            message TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

    print("[DB] Initialised — complaints.db ready.")


# ---------------------------------------------------------------------------
# Create complaint immediately after upload
# Used BEFORE background processing starts
# This prevents frontend polling from getting 404 errors
# ---------------------------------------------------------------------------
def create_pending_complaint(
    tracking_id: str,
    user_id: str,
    video_path: str
):
    conn = _connect()

    conn.execute("""
        INSERT INTO complaints (
            tracking_id,
            user_id,
            video_path,
            submission_status
        )
        VALUES (?, ?, ?, ?)
    """, (
        tracking_id,
        user_id,
        video_path,
        "pending"
    ))

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Update complaint processing status
# Example:
# pending → detecting_issue → mapping_authority → submitted
# ---------------------------------------------------------------------------
def update_status(tracking_id: str, status: str):
    conn = _connect()

    conn.execute("""
        UPDATE complaints
        SET submission_status = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE tracking_id = ?
    """, (status, tracking_id))

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Insert one progress log message
# ---------------------------------------------------------------------------
def insert_log(tracking_id: str, message: str):
    conn = _connect()

    conn.execute("""
        INSERT INTO complaint_logs (tracking_id, message)
        VALUES (?, ?)
    """, (tracking_id, message))

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Fetch all logs for one complaint
# Returned as ordered list of strings
# ---------------------------------------------------------------------------
def fetch_logs(tracking_id: str) -> list[str]:
    conn = _connect()

    rows = conn.execute("""
        SELECT message
        FROM complaint_logs
        WHERE tracking_id = ?
        ORDER BY timestamp ASC
    """, (tracking_id,)).fetchall()

    conn.close()

    return [row["message"] for row in rows]


# ---------------------------------------------------------------------------
# Insert or update full complaint record
# Safe to call multiple times during pipeline
# ---------------------------------------------------------------------------
def save_complaint(ctx: ComplaintContext):
    conn = _connect()

    conn.execute("""
        INSERT INTO complaints (
            tracking_id,
            user_id,
            video_path,

            issue_type,
            location,
            severity,
            transcript,

            authority_name,
            authority_email,
            authority_portal,
            complaint_text,

            submission_status,
            submission_screenshot,

            error
        )
        VALUES (
            :tracking_id,
            :user_id,
            :video_path,

            :issue_type,
            :location,
            :severity,
            :transcript,

            :authority_name,
            :authority_email,
            :authority_portal,
            :complaint_text,

            :submission_status,
            :submission_screenshot,

            :error
        )

        ON CONFLICT(tracking_id) DO UPDATE SET
            issue_type              = excluded.issue_type,
            location                = excluded.location,
            severity                = excluded.severity,
            transcript              = excluded.transcript,

            authority_name          = excluded.authority_name,
            authority_email         = excluded.authority_email,
            authority_portal        = excluded.authority_portal,
            complaint_text          = excluded.complaint_text,

            submission_status       = excluded.submission_status,
            submission_screenshot   = excluded.submission_screenshot,

            error                   = excluded.error,
            updated_at              = CURRENT_TIMESTAMP
    """, {
        "tracking_id": ctx.tracking_id,
        "user_id": ctx.user_id,
        "video_path": ctx.video_path,

        "issue_type": ctx.issue_type,
        "location": ctx.location,
        "severity": ctx.severity,
        "transcript": ctx.transcript,

        "authority_name": ctx.authority_name,
        "authority_email": ctx.authority_email,
        "authority_portal": ctx.authority_portal,
        "complaint_text": ctx.complaint_text,

        "submission_status": ctx.submission_status,
        "submission_screenshot": ctx.submission_screenshot,

        "error": ctx.error
    })

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Fetch one complaint by tracking ID
# Returns full complaint dict
# ---------------------------------------------------------------------------
def fetch_complaint(tracking_id: str) -> Optional[dict]:
    conn = _connect()

    row = conn.execute("""
        SELECT *
        FROM complaints
        WHERE tracking_id = ?
    """, (tracking_id,)).fetchone()

    conn.close()

    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Fetch slim complaint list for dashboard
# Used by mobile app complaint history page
# ---------------------------------------------------------------------------
def fetch_slim_complaints(user_id: str = None) -> list[dict]:
    conn = _connect()

    query = """
        SELECT
            tracking_id,
            submission_status,
            issue_type,
            location,
            severity,
            created_at
        FROM complaints
        {}
        ORDER BY created_at DESC
    """.format("WHERE user_id = ?" if user_id else "")

    params = (user_id,) if user_id else ()

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return [dict(row) for row in rows]