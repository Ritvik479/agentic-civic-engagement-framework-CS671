# This MUST be at the very top, before any other imports
from dotenv import load_dotenv
from pathlib import Path

# Load .env from project root (assuming project-root/app/main.py)
project_root = Path(__file__).parent.parent
env_path = project_root / '.env'
load_dotenv(dotenv_path=env_path)

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import init_db
from app.routes.api import router

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.tools.pair_b.escalation_engine_tool import _run_escalation_check_async

scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[Server] Starting up...")

    await init_db()
    print("[Server] Database initialized.")

    scheduler.add_job(_run_escalation_check_async, "interval", minutes=30)
    scheduler.start()
    print("[Server] Escalation scheduler started.")

    print("[Server] All endpoints live at /api/...")

    yield

    scheduler.shutdown()
    print("[Server] Shutdown complete.")


app = FastAPI(
    title="Agentic Civic Engagement Backend",
    description="Converts activist videos into government complaints.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")