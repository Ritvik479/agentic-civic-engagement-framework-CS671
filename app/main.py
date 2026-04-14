# app/main.py
# ---------------------------------------------------------------------------
# FastAPI entry point
#
# Start server:
#   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
#
# This file:
# - creates FastAPI app
# - enables CORS for frontend mobile app
# - initializes SQLite DB at startup
# - registers all API routes
# ---------------------------------------------------------------------------

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import init_db
from app.routes.api import router


# ---------------------------------------------------------------------------
# Lifespan startup hook (modern FastAPI replacement for @on_event)
# Runs once when server starts
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[Server] Starting up...")

    # Initialize SQLite database
    init_db()

    print("[Server] Database initialized.")
    print("[Server] All endpoints live at /api/...")

    yield

    print("[Server] Shutdown complete.")


# ---------------------------------------------------------------------------
# Create FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Agentic Civic Engagement Backend",
    description="Converts activist videos into government complaints.",
    version="1.0.0",
    lifespan=lifespan
)


# ---------------------------------------------------------------------------
# Enable CORS for mobile frontend access
#
# NOTE:
# For development:
# allow_origins=["*"] is okay.
#
# For production:
# replace "*" with actual frontend domain/IP.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Register all API routes
# All endpoints become:
# /api/process
# /api/status/{id}
# /api/confirm-location
# etc.
# ---------------------------------------------------------------------------
app.include_router(router, prefix="/api")