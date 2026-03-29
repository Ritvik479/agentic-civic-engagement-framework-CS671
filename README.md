# 🧠 Agentic Civic Complaint System

An intelligent backend system that converts citizen-uploaded videos (or social media links) into structured government complaints using Computer Vision, NLP, and Agentic AI.

---

## 👥 Team Structure & Roles

### 🔹 Pair A — Mobile App (Frontend)
**Members:** Vitthal, Hritika

**Responsibilities:**
- Video upload (camera + file picker)
- Location confirmation UI
- API calls to backend: `POST /process`, `POST /confirm-location`, `GET /status/:id`
- Local storage of complaint history (AsyncStorage)

---

### 🔹 Pair B — Backend + Agent Orchestration
**Members:** Ritvik, Vidhi

**Responsibilities:**
- FastAPI server (all endpoints)
- SmolAgents orchestration (agent loop)
- Context schema design (**CRITICAL**)
- SQLite database (tracking + status)
- Agent 5: Playwright (portal submission)
- Agent 6: Escalation logic

---

### 🔹 Trio C — Authority Mapping + LLM + Severity
**Members:** Palak, Vrinda, Himank

**Responsibilities:**
- Authority mapping (JSON dataset)
- Severity scoring (LLM)
- Complaint drafting (LLM)
- Escalation routing logic

---

### 🔹 Pair D — Vision + Speech + Location
**Members:** Vaishnavi, Aishna

**Responsibilities:**
- Video download (yt-dlp)
- Audio extraction + transcription (Whisper)
- Frame extraction (OpenCV)
- Vision analysis (Groq Vision)
- Issue detection (YOLOv8 + LLM)
- Location resolution (weighted model)

---

## 📁 Project Structure
```
project-root/
│
├── app/
│   ├── main.py
│   ├── routes/
│   ├── agents/
│   ├── tools/
│   │   ├── pair_d/
│   │   ├── trio_c/
│   │   └── pair_b/
│   ├── db/
│   └── schemas/
│
├── configs/
│   └── authority_data.json
│
├── data/
├── scripts/
├── tests/
│
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 🧩 File Structure Explained

### `app/`
Main backend codebase.

- **`main.py`** — Entry point of the FastAPI server; registers all routes.
- **`routes/`** — Defines API endpoints (`/process`, `/status`, etc.); handles request → response mapping only.
- **`agents/`** — Controls the pipeline via SmolAgents; registers tools and defines execution logic.
- **`tools/`** — All agent tools grouped by team:
  - `pair_d/` → extraction, CV, location
  - `trio_c/` → authority, severity, drafting
  - `pair_b/` → submission, escalation
  
  > 👉 Each team **only** works in their own folder.

- **`db/`** — SQLite logic; stores complaints, status, and tracking IDs.
- **`schemas/`** — Defines all shared data structures: Context object (**most important**), request schema, response schema.

### `configs/`
Static data (authority mapping JSON). Maintained by Trio C.

### `data/`
Sample inputs (videos, links).

### `scripts/`
Testing and debug scripts.

### `tests/`
Optional unit/integration tests.

---

## 🔐 Secrets & Configuration

### `.env` — Secrets File

Stores sensitive data like API keys. **Never commit this file.**
```env
GROQ_API_KEY=your_api_key_here
OPENAI_API_KEY=your_api_key_here
```

**Reading it in Python:**
```python
from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv("GROQ_API_KEY")
```

### `.env.example` — Template for the team
```env
GROQ_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
```

### `.gitignore`

Prevents secrets and unnecessary files from being tracked by Git.
```
venv/
__pycache__/
*.pyc
.env
*.db
```

---

## 📦 Dependencies

### Core (Everyone installs)
```
fastapi
uvicorn
pydantic
python-dotenv
requests
```

### Pair B — Backend
```
smolagents
playwright
```
After installing, run:
```bash
playwright install
```

### Trio C — LLM
```
openai   # or groq
```

### Pair D — Vision/Speech (Heavy)
```
yt-dlp
opencv-python
ultralytics
whisper
ffmpeg
geopy
```
> ⚠️ May require a GPU — use Google Colab if needed.

---

## 🌿 GitHub Workflow

### Branches

| Branch | Purpose |
|---|---|
| `main` | Stable, reviewed code only |
| `pair-a` | Pair A working branch |
| `pair-b` | Pair B working branch |
| `trio-c` | Trio C working branch |
| `pair-d` | Pair D working branch |

### Daily Workflow

**Before starting work:**
```bash
git pull origin <your-branch>
```

**After making changes:**
```bash
git add .
git commit -m "Clear, descriptive message"
git push origin <your-branch>
```

### Commit Message Guidelines

| ✅ Good | ❌ Bad |
|---|---|
| `Add YOLO-based issue detection` | `update` |
| `Fix location resolution bug` | `changes` |

### Pull Requests

- Required before merging into `main`
- Must be reviewed and approved by at least one teammate

### Merge Checklist

Only merge when:
- [ ] Code runs without errors
- [ ] No breaking changes introduced
- [ ] Compatible with the shared schema

### Resolving Merge Conflicts

Conflicts occur when two people edit the same file. To resolve:
1. Open the conflicted file
2. Manually choose the correct code
3. Remove conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`)
4. Re-commit the resolved file

---

## ⚠️ Important Rules

1. **Always pull before working** — prevents overwriting others' changes.
2. **Do not modify other teams' folders** — avoids unnecessary conflicts.
3. **Follow the schema strictly** — breaking the schema breaks the entire pipeline.
4. **Test your tool independently** — each tool should work as: `input → output`.
5. **Keep commits small and frequent** — easier to debug and merge.

---

## 🚀 Development Order

1. Set up the environment
2. Finalize the context schema
3. Build tools independently
4. Start integration early
5. Test the end-to-end pipeline

---

## 🧠 Final Note

> This system works only if:
> **Clear structure + Shared schema + Clean collaboration = Successful integration**