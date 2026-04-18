# =========================
# 📦 IMPORTS
# =========================
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
import os
import uuid
import time

# PDF generation (placeholder report)
from reportlab.pdfgen import canvas

app = FastAPI()

# =========================
# 📁 STORAGE SETUP
# =========================

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# =========================
# 🧠 IN-MEMORY JOB STORE (PLACEHOLDER)
# =========================
# ❗ In production → replace with DB (PostgreSQL / Redis)

jobs = {}

# =========================
# 📄 PDF GENERATION (PLACEHOLDER AGENT OUTPUT)
# =========================
def generate_pdf(file_path, job_id):
    pdf_path = f"{file_path}.pdf"

    c = canvas.Canvas(pdf_path)
    c.drawString(100, 750, f"Complaint Report - {job_id}")
    c.drawString(100, 700, "Issue: Pothole detected")
    c.drawString(100, 680, "Severity: High")
    c.save()

    return pdf_path


# =========================
# 🤖 AGENT (PLACEHOLDER)
# =========================
# ❗ Replace this with your real AI/ML agent later

def run_agent(job_id, file_path):
    print(f"🤖 Agent started for {job_id}")

    time.sleep(5)  # simulate processing time

    # generate fake report
    pdf_path = generate_pdf(file_path, job_id)

    jobs[job_id]["status"] = "completed"
    jobs[job_id]["result"] = {
        "report": "Pothole detected",
        "severity": "high",
        "pdf": pdf_path
    }

    print(f"✅ Job {job_id} completed")


# =========================
# 🚀 UPLOAD ENDPOINT
# =========================
@app.post("/process")
async def process_video(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    latitude: float = Form(...),
    longitude: float = Form(...)
):
    print("\n📥 REQUEST RECEIVED")

    # =========================
    # 🆔 Generate Job ID
    # =========================
    job_id = f"job_{uuid.uuid4().hex[:8]}"

    # =========================
    # 💾 Save Video File
    # =========================
    ext = video.filename.split('.')[-1]
    file_path = os.path.join(UPLOAD_DIR, f"{job_id}.{ext}")

    with open(file_path, "wb") as f:
        f.write(await video.read())

    print("💾 File saved:", file_path)

    # =========================
    # 📦 Create Job Entry
    # =========================
    jobs[job_id] = {
        "status": "processing",
        "file": file_path,
        "location": {
            "lat": latitude,
            "lng": longitude
        },
        "result": None
    }

    # =========================
    # ⚡ Run Agent in Background
    # =========================
    background_tasks.add_task(run_agent, job_id, file_path)

    # =========================
    # 📤 RESPONSE (IMMEDIATE)
    # =========================
    return {
        "success": True,
        "data": {
            "jobId": job_id,
            "status": "processing"
        }
    }


# =========================
# 📊 JOB STATUS ENDPOINT
# =========================
@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)

    if not job:
        return {
            "success": False,
            "error": "Job not found"
        }

    return {
        "success": True,
        "data": job
    }


# =========================
# 🧪 ROOT TEST ENDPOINT
# =========================
@app.get("/")
def root():
    return {"message": "Backend is running"}