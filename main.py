"""
AI Research Agent - Main Entry Point
Serves the FastAPI backend and the frontend static files.
"""

import os
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.routes import router


# ── Lifespan ──────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n" + "=" * 60)
    print("  [*] AI Research Agent -- Multi-Agent AI Lab")
    print("  [>] Server running at: http://localhost:8000")
    print("  [>] Open your browser to start researching!")
    print("=" * 60 + "\n")
    yield
    print("\n[*] Server shutting down.")


# ── Create App ────────────────────────────────────────────────

app = FastAPI(
    title="AI Research Agent",
    description="Autonomous Research Scientist Agent -- Multi-Agent AI Lab",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router)

# ── Serve Frontend ────────────────────────────────────────────

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")

# Mount static files
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
async def serve_frontend():
    """Serve the main frontend page."""
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


# ── Run ───────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
