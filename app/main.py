from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.transcription import router as transcription_router


STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Startup Interview API", version="0.1.0")
app.include_router(transcription_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health")
async def health() -> dict[str, str]:
    """Check that the application responds; external providers are not checked."""
    return {"status": "ok"}


@app.get("/", response_class=FileResponse, include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
