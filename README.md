# 🧠 Agentic Civic Engagement Framework

An intelligent system that converts citizen-captured media (videos or images) into structured, formally submitted government complaints — using computer vision, language models, RAG-based legal citation, browser automation, and an agent-based orchestration pipeline.

---

## 🚀 Overview

This project implements an **agentic pipeline** that:

1. Accepts citizen-uploaded media (video or image) via a mobile app
2. Extracts the issue type, severity, and location using multimodal AI
3. Retrieves relevant legal citations via semantic search over environmental law
4. Maps the issue to the appropriate government authority based on state, district, and severity
5. Drafts a formal complaint and submits it via portal, email, and/or WhatsApp
6. Tracks complaint status and automatically escalates unresolved complaints to higher authority levels
7. Automates submission to **CPGRAMS** (Central Public Grievance Redress and Monitoring System) via a browser agent

The system targets **environmental and civic issues** such as:
- Pollution incidents (air, water, noise)
- Waste management violations
- Infrastructure problems
- Sustainability and public health concerns

---

## 🧩 Architecture

```
Orchestrator (smolagents ToolCallingAgent — max 10 steps)
        |
        ├── vision_tool              [Perception]
        ├── route_to_authority       [Reasoning]
        ├── complaint_assembly_tool  [Reasoning]
        └── submission_tool          [Execution]

Supporting Systems:
  Async SQLite (aiosqlite)  —  pipeline stage logging & status polling
  Escalation Scheduler      —  SLA-breach detection, runs every 30 min
```

All layers are coordinated by a central **smolagents-based orchestrator** using a `ToolCallingAgent` with a shared `FinalComplaint` state object passed across tools.

---

## 📁 Project Structure

```
project-root/
│
├── app/
│   ├── main.py                  # FastAPI server, DB init, escalation scheduler
│   ├── orchestrator.py          # smolagents ToolCallingAgent pipeline controller
│   ├── context.py               # Shared ComplaintContext dataclass
│   ├── constants.py             # Pipeline stages, SLA policies, routing rules, thresholds
│   ├── validators.py            # Pydantic model validators (MediaMetadata, FinalComplaint, etc.)
│   ├── routes/
│   │   └── api.py               # All FastAPI endpoints
│   ├── db/
│   │   └── database.py          # Async SQLite layer (aiosqlite), complaints + logs tables
│   ├── schemas/
│   │   ├── issue_schema.py      # Core Pydantic models: ExtractedIssue, FinalComplaint, etc.
│   │   ├── requests.py          # Inbound request schemas
│   │   └── responses.py         # Outbound response schemas
│   ├── browser_agent/           # CPGRAMS browser automation (ReACT loop via Playwright + LLM)
│   │   ├── main.py              # ReACT loop entry point (Observe → Think → Act → Record)
│   │   ├── config.py            # System goal, credentials, NVIDIA API key, complaint payload
│   │   ├── browser_tools.py     # Playwright environment setup (headed Chromium)
│   │   ├── observer.py          # DOM scraper → structured JSON for LLM
│   │   ├── planner_llm.py       # NVIDIA Nemotron LLM brain (Thought + Action JSON)
│   │   ├── planner.py           # Rule-based fallback planner (login flow)
│   │   ├── executor.py          # Action JSON → Playwright commands (fill, click, navigate)
│   │   └── memory.py            # State flags + full ReACT history trace
│   └── tools/
│       ├── pair_d/              # Perception agents
│       │   ├── content_extractor_tool.py
│       │   ├── issue_detector_tool.py
│       │   ├── location_resolver_tool.py
│       │   ├── vision_pipeline_tool.py
│       │   └── vision_tool_wrapped.py
│       ├── trio_c/              # Reasoning agents
│       │   ├── authority_lookup_tool.py
│       │   ├── complaint_assembly_tool_wrapped.py
│       │   ├── complaint_draft_tool.py
│       │   ├── severity_score_tool.py
│       │   └── smart_rag_tool.py
│       └── pair_b/              # Execution agents
│           ├── email_dispatch_tool.py
│           ├── escalation_engine_tool.py
│           ├── portal_navigator_tool.py
│           ├── submission_agent_tool.py
│           ├── submission_tool_wrapped.py
│           └── whatsapp_dispatch_tool.py
│
├── frontend/                    # React Native (Expo) mobile app
├── dummy_portal/                # Simulated complaint portal (Flask + HTML templates)
├── configs/
│   └── authority_data.json      # Authority contacts by state/district/issue/level
├── data/
│   ├── test_vision/             # Sample media for testing
│   └── environmental_laws.txt   # RAG corpus for legal citation
│
├── .env
├── requirements.txt
└── README.md
```

---

## ⚙️ Setup & Installation

### Prerequisites
- Python 3.10+
- Node.js 18+
- `ffmpeg` installed and available in PATH
- NVIDIA, Groq, or OpenAI API key

---

### 1. Environment Variables

Create a `.env` file in the project root:

```env
# LLM Backend — choose "hf" (Hugging Face) or "litellm"
ORCHESTRATOR_LLM=hf

# Hugging Face (default)
HF_TOKEN=your_hf_token
HF_MODEL_ID=Qwen/Qwen2.5-72B-Instruct

# LiteLLM (optional alternative)
LITELLM_MODEL=openai/gpt-4o
LITELLM_API_KEY=your_key
LITELLM_BASE_URL=

# Groq (used by Pair D vision tools)
GROQ_API_KEY=your_groq_key

# NVIDIA Nemotron (used by browser_agent)
NVIDIA_API_KEY=your_nvidia_key
NVIDIA_MODEL=
NVIDIA_BASE_URL=
```

Frontend (`frontend/.env`):
```env
EXPO_PUBLIC_API_URL=http://<your-ip>:8000
```

Ensure your phone and development machine are on the same network when testing the mobile app.

---

### 2. Install Dependencies

```bash
# Backend
cd project-root
python -m venv venv
source venv/bin/activate        # macOS/Linux
venv\Scripts\activate           # Windows
pip install -r requirements.txt
playwright install chromium

# Frontend
cd frontend
npm install
```

---

### 3. Run the System

Open multiple terminals:

#### Backend
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

#### Frontend
```bash
cd frontend
npx expo start
```

#### Dummy Portal (for local submission testing)
```bash
cd dummy_portal
python app.py
```

#### CPGRAMS Browser Agent (standalone)
```bash
python -m app.browser_agent.main
```

---

## 🔌 API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/process` | POST | Upload media (file or URL) to start the complaint pipeline |
| `/api/status/{id}` | GET | Poll current pipeline status and step-by-step logs |
| `/api/confirm-location` | POST | User confirms or corrects the system-inferred location |
| `/api/complaint/{id}` | GET | Retrieve full complaint details |
| `/api/complaints` | GET | List all complaints for a given user |
| `/api/health` | GET | Server health check |

All endpoints are prefixed with `/api`. The pipeline is non-blocking — `/api/process` returns a `tracking_id` immediately and the pipeline runs in the background.

---

## 🧠 Agent Design

### Perception Layer — Pair D

Processes raw media into structured issue data:

- **Content Extractor**: Acquires video frames (YOLO-scored for outdoor civic scenes), generates transcripts via embedded subtitles, YouTube auto-subs, or Whisper, and performs OCR on visible text.
- **Issue Detector**: Classifies the civic issue using YOLO object detection, a vision-language model fallback, and multimodal LLM refinement against the transcript.
- **Location Resolver**: Triangulates location from visual cues (shop signs, architecture), speech mentions, and user-provided geotag using a weighted resolution strategy and Nominatim geocoding.
- **Vision Pipeline**: Orchestrates the three agents above into a single tool call returning `ExtractedIssue`.

### Reasoning Layer — Trio C

Converts extracted issue data into a formal, routable complaint:

- **Authority Lookup**: Matches state + district + issue category + severity to the correct government department from `authority_data.json`, supporting up to 4 escalation levels (local DC → state board → CPCB → CPGRAMS).
- **Severity Scorer**: Uses an LLM to assign a severity score (1–5), where 1–4 map to escalation levels in the authority data and 5 bypasses local/state authorities to directly contact the central authority
- **Smart RAG**: Performs semantic similarity search over `environmental_laws.txt` to retrieve relevant legal citations for the complaint.
- **Complaint Drafter**: Combines issue metadata, legal citations, and authority details to generate a factual, formal complaint via LLM.
- **Complaint Assembler**: Packages the drafted text and all metadata into a validated `FinalComplaint` object.

### Execution Layer — Pair B

Handles multi-channel submission and follow-up:

- **Submission Agent**: Orchestrates portal, email, and WhatsApp dispatch in sequence, ensuring submission succeeds through at least one channel.
- **Portal Navigator**: Uses Playwright browser automation to fill and submit the complaint form on the target portal, capturing the reference ID from the confirmation page.
- **Email Dispatch**: Sends formal complaint emails via SMTP or logs the payload locally for testing.
- **WhatsApp Dispatch**: Sends a complaint summary alert to the authority's registered number via Twilio or Meta Cloud API.
- **Escalation Engine**: A scheduled job (runs every 30 minutes) that checks the database for complaints exceeding their SLA deadline and re-submits to the next authority level.

---

## 🌐 CPGRAMS Browser Agent

A self-contained ReACT (Reason + Act) browser automation agent that submits complaints directly to the Central Public Grievance Redress and Monitoring System ([pgportal.gov.in](https://pgportal.gov.in)).

**Loop:** Observe → Think → Act → Record, up to 25 steps.

| Module | Role |
|---|---|
| `observer.py` | Scrapes interactive DOM elements into structured JSON for the LLM |
| `planner_llm.py` | NVIDIA Nemotron LLM brain — outputs a `Thought` + structured `Action` JSON |
| `planner.py` | Rule-based fallback for the login flow (username, password, CAPTCHA, submit) |
| `executor.py` | Translates Action JSON into Playwright commands (`fill`, `click`, `select`, `navigate`) |
| `memory.py` | Tracks state flags and the full ReACT history trace across turns |
| `browser_tools.py` | Launches headed Chromium — keeps the browser visible so the user can solve CAPTCHAs |

The agent runs in **headed mode** by design: when a CAPTCHA is encountered, execution pauses and prompts the user for terminal input before continuing.

---

## 🔄 Escalation System

Severity levels map to SLA response windows. A background scheduler checks every 30 minutes for complaints that have breached their deadline and automatically re-submits to the next authority level:

```
Level 1 → District / Local Authority
Level 2 → State-level Board (e.g., Punjab Pollution Control Board)
Level 3 → Central Board (e.g., CPCB)
Level 4 → CPGRAMS (national grievance portal)
Level 5 → Direct bypass to Central Authority (CPCB / CPGRAMS), skipping Levels 1–4
```

---

## 🗺️ Authority Coverage

`authority_data.json` currently covers the following states across all issue categories and all 4 escalation levels:

**Assam · Delhi · Gujarat · Haryana · Himachal Pradesh · Kerala · Punjab · Uttar Pradesh**

---

## 🧩 Key Design Principles

- **Agentic Architecture** — Independent tool-agents handle perception, reasoning, and execution, each with a single well-defined responsibility.
- **smolagents Orchestration** — A `ToolCallingAgent` manages tool sequencing and state transitions via a task prompt, with up to 10 steps per pipeline run.
- **Shared Context Object** — `FinalComplaint` (Pydantic model) is the orchestrator-level state object passed between tool calls and persisted to the database. `ComplaintContext` is an internal dataclass used within Pair B tools for local state management during submission.   
- **Database-Backed State Machine** — Async SQLite (`aiosqlite`) provides persistence, observability, and recovery. Every pipeline step is logged for frontend polling.
- **Human-in-the-Loop** — Users can confirm or correct inferred locations before authority mapping. CPGRAMS CAPTCHA resolution is also human-assisted.
- **Multi-Channel Redundancy** — Complaints are submitted via portal → email → WhatsApp in order of priority; failure in one channel does not block the others.
- **RAG-Augmented Drafting** — Complaint text is grounded in actual environmental law via semantic search, improving legal credibility.
- **Asynchronous Execution** — The pipeline runs in a background task; the API returns immediately with a tracking ID.

---

## ⚠️ Notes

- A **dummy complaint portal** is included for testing submission flows locally without hitting real government systems.
- Real-world deployment requires integration with live government APIs and portals beyond CPGRAMS.
- Vision and LLM components may require significant compute; Groq inference is used where latency is critical.
- The confidence discard threshold is set at **0.20**; issues below this are dropped. Human review is flagged below **0.50**.

---

## 📌 Future Improvements

- Expanded authority coverage to all Indian states and union territories
- Integration with additional real government APIs (beyond CPGRAMS)
- Smarter escalation policies based on issue category, not just severity
- Multilingual support for regional language transcripts and complaints
- Real-time push notifications (replacing frontend polling)
- Verified location resolution using satellite/street-level imagery

---

## 🧠 Summary

This system demonstrates how **AI agents can automate civic engagement workflows end-to-end** — from a citizen filming a pothole on their phone to a formally drafted, legally cited complaint landing in the inbox of the right government authority, with automatic follow-up if it goes unresolved.