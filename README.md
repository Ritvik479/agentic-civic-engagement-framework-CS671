# 🧠 Agentic Civic Engagement Framework

An intelligent system that converts citizen-captured media (videos or images) into structured government complaints using computer vision, language models, and an agent-based orchestration pipeline.

---

## 🚀 Overview

This project implements an **agentic pipeline** that:

1. Extracts insights from user-submitted media  
2. Identifies the nature and location of the issue  
3. Maps it to the appropriate government authority  
4. Generates a formal complaint  
5. Submits it via multiple channels (portal, email, etc.)  
6. Tracks status and supports escalation  

The system is designed for **environmental and civic issues** such as:
- Pollution incidents  
- Waste management violations  
- Infrastructure problems  
- Sustainability concerns  

---

## 🧩 Architecture
```
Perception (Vision + Speech)
↓
Reasoning (Authority + Severity + Drafting)
↓
Execution (Submission + Escalation)
```

- **Perception Layer (Pair D)**: Extracts issue type, transcript, and location  
- **Reasoning Layer (Trio C)**: Determines authority, severity, and complaint text  
- **Execution Layer (Pair B)**: Handles submission and escalation  
- **Orchestrator**: Coordinates all agents using a shared context  

---

## 📁 Project Structure
```
project-root/
│
├── app/ # Backend (FastAPI + orchestration)
│ ├── main.py # Server entry point
│ ├── orchestrator.py # Core pipeline controller
│ ├── context.py # Shared context object
│ ├── routes/ # API endpoints
│ ├── db/ # Database layer
│ ├── schemas/ # Request/response models
│ └── tools/ # Agent tools
│ ├── pair_d/ # Perception agents
│ ├── trio_c/ # Reasoning agents
│ └── pair_b/ # Execution agents
│
├── frontend/ # React Native (Expo) app
├── dummy_portal/ # Simulated complaint portal
├── configs/ # Static authority data
├── data/ # Test inputs and datasets
├── scripts/ # Testing utilities
│
├── .env # Environment variables (not committed)
├── requirements.txt
└── README.md
```


---

## ⚙️ Setup & Installation

### Prerequisites
- Python 3.10+
- Node.js 18+
- `ffmpeg` installed and available in PATH
- API key (e.g., Groq/OpenAI)

---

### 1. Environment Variables

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_api_key_here
```

Frontend (`frontend/.env`):
```env
EXPO_PUBLIC_API_URL=http://<your-ip>:8000
```

Ensure your phone and development machine are on the same network when testing the mobile app.

### 2. Install Dependencies
```bash
# Backend
cd project-root
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
playwright install chromium

# Frontend
cd frontend
npm install
```

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
#### Dummy Portal
```bash
cd dummy_portal
python app.py
```
(Optional) Run test script:
```bash
python scripts/test_e2e.py
```

---

## 🔌 API Endpoints

| Endpoint | Method | Description |
|--------|--------|------------|
| `/api/process` | POST | Upload media / provide URL to start pipeline |
| `/api/status/{id}` | GET | Get current status + logs |
| `/api/confirm-location` | POST | User confirms detected location |
| `/api/complaint/{id}` | GET | Full complaint details |
| `/api/complaints` | GET | List user complaints |
| `/api/health` | GET | Health check |

---

## 🧠 Key Design Principles

- **Agentic Architecture**  
  Independent components (agents) handle perception, reasoning, and execution.

- **Orchestrator-Controlled Pipeline**  
  A central async controller manages execution flow and state transitions.

- **Shared Context Object**  
  Ensures consistent data flow across all agents.

- **Database-Backed State Machine**  
  Enables persistence, observability, and recovery.

- **Human-in-the-Loop**  
  Users can confirm or correct system-inferred locations.

- **Asynchronous Execution**  
  Long-running tasks run in the background without blocking API responses.

---

## 🔄 Escalation System

A scheduled job periodically checks unresolved complaints and escalates them to higher authorities when needed.

---

## ⚠️ Notes

- This project includes a **dummy complaint portal** for testing submission flows.  
- Real-world deployment would require integration with actual government systems.  
- Some components (vision, LLMs) may require significant compute resources.

---

## 📌 Future Improvements

- Integration with real government APIs  
- Smarter escalation policies  
- Better location resolution  
- Multilingual support  
- Real-time notifications (instead of polling)

---

## 🧠 Summary

This system demonstrates how **AI agents can automate civic engagement workflows**, bridging the gap between citizen reporting and government action.