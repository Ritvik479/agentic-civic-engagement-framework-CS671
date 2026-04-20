"""
dummy_portal/app.py
-------------------
Standalone Flask app simulating a government complaint portal.
Used for testing Agent 5 (Playwright form fill) and Agent 6 (escalation polling).

No authentication required.
Run: python dummy_portal/app.py
"""

import sqlite3
import os
import datetime
import uuid

from flask import Flask, render_template, request, redirect, url_for, jsonify, g

app = Flask(__name__)

# ---------------------------------------------------------------------------
# DB setup
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(__file__), "dummy_complaints.db")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with app.app_context():
        db = get_db()
        db.executescript("""
            CREATE TABLE IF NOT EXISTS portal_complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                complaint_ref_id TEXT UNIQUE NOT NULL,
                tracking_id TEXT,

                submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,

                full_name TEXT,
                email TEXT,
                phone TEXT,

                issue_type TEXT,
                state TEXT,
                district TEXT,
                location_label TEXT,
                severity INTEGER,

                description TEXT,
                authority_name TEXT,

                status TEXT DEFAULT 'Received',
                admin_note TEXT DEFAULT '',

                clock_offset_hours INTEGER DEFAULT 0
            );
        """)
        db.commit()
    print("[DummyPortal] DB initialised.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
STATUSES = ["Received", "Acknowledged", "Under Review", "Resolved", "Rejected"]

def effective_age_hours(submitted_at_str: str, individual_offset: int) -> float:
    """Returns complaint age in hours, adding per-complaint offset."""
    try:
        submitted_at = datetime.datetime.strptime(
            submitted_at_str, "%Y-%m-%d %H:%M:%S"
        )
    except ValueError:
        submitted_at = datetime.datetime.now()

    real_age = (datetime.datetime.now() - submitted_at).total_seconds() / 3600
    return real_age + (individual_offset or 0)


def generate_ref_id() -> str:
    date_str = datetime.datetime.now().strftime("%Y%m%d")
    short = uuid.uuid4().hex[:6].upper()
    return f"COMP-{date_str}-{short}"


# ---------------------------------------------------------------------------
# PUBLIC ROUTES (Playwright navigates these)
# ---------------------------------------------------------------------------

@app.route("/")
def home():
    """Landing page — Playwright starts here."""
    return render_template("home.html")


@app.route("/complaint/new", methods=["GET"])
def complaint_form():
    """Multi-field complaint form — Playwright fills and submits this."""
    return render_template("complaint_form.html")


@app.route("/complaint/submit", methods=["POST"])
def complaint_submit():
    """Receives form POST, creates complaint record, redirects to confirmation."""
    db = get_db()

    ref_id = generate_ref_id()

    db.execute("""
        INSERT INTO portal_complaints (
            complaint_ref_id, tracking_id,
            full_name, email, phone,
            issue_type, state, district, location_label, severity,
            description, authority_name
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ref_id,
        request.form.get("tracking_id", ""),
        request.form.get("full_name", ""),
        request.form.get("email", ""),
        request.form.get("phone", ""),
        request.form.get("issue_type", ""),
        request.form.get("state", ""),
        request.form.get("district", ""),
        request.form.get("location_label", ""),
        None,
        request.form.get("description", ""),
        request.form.get("authority_name", ""),
    ))
    db.commit()

    return redirect(url_for("complaint_confirmation", ref_id=ref_id))


@app.route("/complaint/confirm/<ref_id>")
def complaint_confirmation(ref_id):
    """
    Confirmation page shown after successful submission.
    Playwright extracts the complaint_ref_id from this page.
    The ref_id is in an element with id='complaint-ref-id' for easy scraping.
    """
    return render_template("confirmation.html", ref_id=ref_id)


@app.route("/complaint/status", methods=["GET", "POST"])
def complaint_status():
    """
    Status check page — user/Agent 6 enters complaint ID and sees status.
    Agent 6 can also use the JSON API endpoint below instead.
    """
    complaint = None
    error = None

    if request.method == "POST":
        ref_id = request.form.get("ref_id", "").strip()
        db = get_db()
        row = db.execute(
            "SELECT * FROM portal_complaints WHERE complaint_ref_id = ?",
            (ref_id,)
        ).fetchone()

        if row:
            age = effective_age_hours(
                row["submitted_at"],
                row["clock_offset_hours"]
            )
            complaint = dict(row)
            complaint["effective_age_hours"] = round(age, 1)
        else:
            error = f"No complaint found with ID: {ref_id}"

    return render_template("status.html", complaint=complaint, error=error)


# ---------------------------------------------------------------------------
# JSON API — for Agent 6 programmatic polling (no Playwright needed)
# ---------------------------------------------------------------------------

@app.route("/api/complaint/<ref_id>", methods=["GET"])
def api_get_complaint(ref_id):
    """Agent 6 polls this to check status without scraping HTML."""
    db = get_db()
    row = db.execute(
        "SELECT * FROM portal_complaints WHERE complaint_ref_id = ?",
        (ref_id,)
    ).fetchone()

    if not row:
        return jsonify({"error": "Not found"}), 404

    age = effective_age_hours(
        row["submitted_at"],
        row["clock_offset_hours"]
    )

    data = dict(row)
    data["effective_age_hours"] = round(age, 1)
    return jsonify(data)


# ---------------------------------------------------------------------------
# ADMIN ROUTES
# ---------------------------------------------------------------------------

@app.route("/admin")
def admin_panel():
    """Admin dashboard — view all complaints, update status, control clock."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM portal_complaints ORDER BY submitted_at DESC"
    ).fetchall()

    complaints = []
    for row in rows:
        c = dict(row)
        c["effective_age_hours"] = round(
            effective_age_hours(
                row["submitted_at"],
                row["clock_offset_hours"]
            ), 1
        )
        complaints.append(c)

    return render_template(
        "admin.html",
        complaints=complaints,
        statuses=STATUSES,
    )


@app.route("/admin/update_status", methods=["POST"])
def admin_update_status():
    """Admin sets complaint status + optional note."""
    db = get_db()
    ref_id = request.form.get("complaint_ref_id")
    new_status = request.form.get("status")
    note = request.form.get("admin_note", "")

    try:
        time_offset = int(request.form.get("time_offset_hours", 0))
        time_offset = max(0, min(time_offset, 8760))
    except ValueError:
        time_offset = 0

    if new_status not in STATUSES:
        return "Invalid status", 400

    db.execute("""
        UPDATE portal_complaints
        SET status = ?, admin_note = ?, clock_offset_hours = ?
        WHERE complaint_ref_id = ?
    """, (new_status, note, time_offset, ref_id))
    db.commit()

    return redirect(url_for("admin_panel"))

@app.route("/admin/delete_complaint", methods=["POST"])
def admin_delete_complaint():
    db = get_db()
    ref_id = request.form.get("complaint_ref_id")

    db.execute(
        "DELETE FROM portal_complaints WHERE complaint_ref_id = ?",
        (ref_id,)
    )
    db.commit()

    return redirect(url_for("admin_panel"))

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    print("[DummyPortal] Running on http://localhost:5050")
    app.run(debug=True, port=5050)