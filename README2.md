# Agentic Civic Complaint System

A mobile application for filing civic complaints through video evidence. Users record or upload a video of a civic issue (e.g. potholes, broken infrastructure), which is sent to an AI pipeline backend that analyzes the footage and generates a structured complaint report with severity assessment.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   React Native App                   │
│                    (Expo SDK)                        │
│                                                      │
│  UploadScreen  ──►  TabNavigator  ──►  TasksScreen  │
│  (record/pick       (navigation)      (job polling) │
│   + location)                                        │
└──────────────────────┬──────────────────────────────┘
                       │ POST /process (multipart)
                       │ GET  /jobs/:id  (polling)
                       ▼
┌─────────────────────────────────────────────────────┐
│                  FastAPI Backend                     │
│                                                      │
│  /process  ──►  save video  ──►  background agent  │
│  /jobs/:id ◄──  job store   ◄──  (AI pipeline)     │
└─────────────────────────────────────────────────────┘
```

**Flow:**
1. User records/selects a video and location is captured automatically.
2. App sends video + GPS coordinates to `POST /process`.
3. Server saves the file, creates a job entry, and returns a `jobId` immediately.
4. AI agent runs in the background — currently a placeholder (5s sleep + fake report).
5. App polls `GET /jobs/:jobId` every 3 seconds until status is `"completed"`.
6. Result screen shows report, severity, and PDF path.

---

## Project Structure

```
/
├── app/
│   ├── screens/
│   │   ├── HomeScreen.jsx          # Dashboard (not included in review)
│   │   ├── UploadScreen.jsx        # Video capture + submit
│   │   └── TasksScreen.jsx         # Job status polling + results
│   └── navigation/
│       └── TabNavigator.jsx        # Bottom tab navigator
├── backend/
│   └── main.py                     # FastAPI server
├── app.json                        # Expo configuration
└── .env                            # EXPO_PUBLIC_API_URL
```

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Node.js | ≥ 18 | React Native / Expo |
| Expo CLI | Latest | Build and dev server |
| Python | ≥ 3.10 | Backend |
| pip | Latest | Python deps |
| Android Studio / Xcode | Latest | Native device builds |

---

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd civic-agent-app
```

### 2. Frontend

```bash
npm install
```

Create a `.env` file in the project root:

```env
EXPO_PUBLIC_API_URL=http://<your-machine-ip>:8000
```

> ⚠️ Use your machine's LAN IP address (e.g. `192.168.1.x`), not `localhost`. The mobile device/emulator needs to reach your machine over the network.

### 3. Backend

```bash
cd backend
pip install fastapi uvicorn python-multipart reportlab
```

Start the server:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Verify it's running:

```bash
curl http://localhost:8000/
# {"message":"Backend is running"}
```

### 4. Run the app

```bash
npx expo start
```

Scan the QR code with **Expo Go** (Android/iOS) or press `a` for Android emulator / `i` for iOS simulator.

---

## API Reference

### `POST /process`

Accepts a video file and GPS coordinates. Returns a job ID immediately; processing happens in the background.

**Request** — `multipart/form-data`

| Field | Type | Description |
|-------|------|-------------|
| `video` | File | Video file (`mp4`, `mov`, etc.) |
| `latitude` | float | GPS latitude |
| `longitude` | float | GPS longitude |

**Response**

```json
{
  "success": true,
  "data": {
    "jobId": "job_367169a6",
    "status": "processing"
  }
}
```

---

### `GET /jobs/:jobId`

Returns the current state of a processing job.

**Response — processing**

```json
{
  "success": true,
  "data": {
    "status": "processing",
    "file": "uploads/job_367169a6.mp4",
    "location": { "lat": 31.7074, "lng": 76.9218 },
    "result": null
  }
}
```

**Response — completed**

```json
{
  "success": true,
  "data": {
    "status": "completed",
    "file": "uploads/job_367169a6.mp4",
    "location": { "lat": 31.7074, "lng": 76.9218 },
    "result": {
      "report": "Pothole detected",
      "severity": "high",
      "pdf": "uploads/job_367169a6.mp4.pdf"
    }
  }
}
```

**Response — not found**

```json
{
  "success": false,
  "error": "Job not found"
}
```

---

## Replacing the Placeholder Agent

The current `run_agent()` in `main.py` is a stub. To plug in a real AI pipeline:

```python
def run_agent(job_id, file_path):
    try:
        # 1. Load the video
        # video_frames = extract_frames(file_path)

        # 2. Run your model
        # result = your_model.predict(video_frames)

        # 3. Generate report
        # pdf_path = generate_real_report(result, job_id)

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["result"] = {
            "report": result.description,
            "severity": result.severity,
            "pdf": pdf_path,
        }
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)
```

The agent receives `job_id` (string) and `file_path` (path to saved video). Location data is available at `jobs[job_id]["location"]`.

---

## Environment Variables

| Variable | Where | Description |
|----------|-------|-------------|
| `EXPO_PUBLIC_API_URL` | `.env` (frontend) | Base URL of the FastAPI backend |

---

## Known Limitations (Current MVP)

These are documented issues to fix before production deployment:

- **In-memory job store** — all jobs are lost on server restart. Replace with Redis or a database.
- **No file size limit** — the server accepts uploads of any size. Large files will exhaust RAM.
- **No authentication** — any client can submit complaints or query job IDs.
- **No file cleanup** — uploaded videos accumulate indefinitely on disk.
- **TasksScreen crashes if opened without a job** — navigating directly to the Processing tab without submitting a complaint will crash the app.
- **PDF served as filesystem path** — the result returns a raw server path, not a downloadable URL.

---

## Android Permissions

Declared in `app.json` and requested at runtime:

| Permission | Usage |
|-----------|-------|
| `CAMERA` | Video recording |
| `RECORD_AUDIO` | Video audio capture |
| `ACCESS_FINE_LOCATION` | GPS coordinates for complaint location |

---

## Dependencies

### Frontend

| Package | Purpose |
|---------|---------|
| `expo-video` | Video playback in preview |
| `expo-image-picker` | Camera + gallery access |
| `expo-location` | GPS coordinates |
| `expo-audio` | Microphone permission |
| `lucide-react-native` | Icons |
| `@react-navigation/bottom-tabs` | Tab navigation |

### Backend

| Package | Purpose |
|---------|---------|
| `fastapi` | Web framework |
| `uvicorn` | ASGI server |
| `python-multipart` | Multipart form parsing |
| `reportlab` | PDF generation (placeholder) |

---

## Contributing

This project is structured so the backend agent and the mobile frontend can be developed independently. The contract between them is the `/process` and `/jobs/:id` API — as long as those responses match the schema above, either side can be swapped out.

When replacing the agent, update `run_agent()` in `main.py`. When updating the result UI, update `TasksScreen.jsx`. The upload and polling logic does not need to change.