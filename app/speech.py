"""ElevenLabs synthesis. Credentials and voice configuration stay on the server."""

import asyncio
import os
import re
from typing import Literal
from urllib.parse import urlsplit

import httpx2
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

router = APIRouter(prefix="/api/speech")
DEFAULT_VOICE = "cjVigY5qzO86Huf0OWal"  # Eric; configurable without code changes.
DEFAULT_MODEL = "eleven_flash_v2_5"


class SpeechRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=4000)
    language: Literal["de", "en"]

    @field_validator("text")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Speech must contain text")
        return value


async def synthesize(text: str, language: str) -> bytes:
    key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise HTTPException(503, "Add ELEVENLABS_API_KEY to .env and recreate the application container.")
    voice = os.getenv("ELEVENLABS_VOICE_ID", DEFAULT_VOICE).strip()
    model = os.getenv("ELEVENLABS_TTS_MODEL", DEFAULT_MODEL).strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", voice) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", model):
        raise HTTPException(503, "Check ELEVENLABS_VOICE_ID and ELEVENLABS_TTS_MODEL in .env.")
    try:
        async with asyncio.timeout(30), httpx2.AsyncClient(timeout=25.0) as client:
            # No automatic retries: a lost response could still have consumed credits.
            async with client.stream(
                "POST", f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                headers={"xi-api-key": key, "Accept": "audio/mpeg"},
                params={"output_format": "mp3_44100_128"},
                json={"text": text, "model_id": model, "language_code": language},
            ) as response:
                if response.status_code in (401, 403):
                    raise HTTPException(502, "ElevenLabs rejected access. Check the API key and Text to Speech permission.")
                if response.status_code == 429:
                    raise HTTPException(503, "ElevenLabs reached a quota or rate limit. Check credits and try again later.")
                if response.status_code != 200:
                    raise HTTPException(502, "ElevenLabs could not generate speech. Check the configured voice and model.")
                if response.headers.get("content-type", "").split(";")[0] != "audio/mpeg":
                    raise HTTPException(502, "ElevenLabs returned an unexpected audio format.")
                audio = bytearray()
                async for chunk in response.aiter_bytes():
                    audio.extend(chunk)
                    if len(audio) > 5_000_000:
                        raise HTTPException(502, "The spoken reply was too large. Please use shorter replies.")
                if not audio:
                    raise HTTPException(502, "ElevenLabs returned no audio.")
                return bytes(audio)
    except (TimeoutError, httpx2.TimeoutException):
        raise HTTPException(504, "Speech generation timed out. The written reply is still available.") from None
    except httpx2.RequestError:
        raise HTTPException(502, "Could not connect to ElevenLabs. The written reply is still available.") from None


@router.post("")
async def speech(body: SpeechRequest, request: Request) -> Response:
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host"):
        raise HTTPException(403, "Cross-origin requests are not allowed")
    audio = await synthesize(body.text, body.language)
    return Response(audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})
