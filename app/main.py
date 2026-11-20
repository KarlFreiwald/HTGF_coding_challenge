from pathlib import Path
from uuid import UUID
from contextlib import asynccontextmanager
from app import storage

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.transcription import router as transcription_router
from app.interview import router as interview_router
from app.speech import router as speech_router


STATIC_DIR = Path(__file__).resolve().parent / "static"

@asynccontextmanager
async def lifespan(app):
    storage.initialize()
    yield


app = FastAPI(title="Startup Interview API", version="0.1.0", lifespan=lifespan)
app.include_router(transcription_router)
app.include_router(interview_router)
app.include_router(speech_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health")
async def health() -> dict[str, str]:
    """Check that the application responds; external providers are not checked."""
    return {"status": "ok"}


@app.get("/", response_class=FileResponse, include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/history", response_class=FileResponse, include_in_schema=False)
async def history_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "history.html")


@app.get("/api/history")
def list_history(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return storage.past_conversations()


@app.get("/api/history/{conversation_id}")
def history_detail(conversation_id: UUID, response: Response):
    saved = storage.snapshot(str(conversation_id))
    if saved is None or saved[0]["status"] == "active":
        raise HTTPException(404, "Past interview not found.")
    settings, messages = saved
    response.headers["Cache-Control"] = "no-store"
    return {"conversation": settings, "messages": messages}
