"""Browser PCM -> AssemblyAI streaming -> browser transcript events."""

import asyncio
import json
import logging
import os
from app import storage, summaries
from app.llm import DEFAULT_MODEL as DEFAULT_INTERVIEW_MODEL, MODELS
from contextlib import suppress
from typing import Literal
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus


router = APIRouter()
logger = logging.getLogger(__name__)
PROVIDER_URL = "wss://streaming.assemblyai.com/v3/ws"
DEFAULT_MODEL = "assemblyai-stt-3-7-realtime-agent"
START_TIMEOUT = 10
FINAL_TIMEOUT = 8
MAX_SESSION_SECONDS = 600


class StartMessage(BaseModel):
    type: Literal["start"]
    language: Literal["de", "en"]
    tone: Literal["professional", "conversational"] = "professional"
    model: str = DEFAULT_INTERVIEW_MODEL
    sample_rate: int = Field(ge=8000, le=48000, strict=True)


class TranscriptionError(Exception):
    """A message safe to show in the browser (never includes provider secrets)."""


def provider_url(start: StartMessage, model: str) -> str:
    return PROVIDER_URL + "?" + urlencode({
        "speech_model": model,
        "sample_rate": start.sample_rate,
        "encoding": "pcm_s16le",
        "language_codes": json.dumps([start.language]),
        "mode": "balanced",
    })


def transcript_event(message: dict) -> dict:
    return {
        "type": "transcript",
        "turn_id": message["turn_order"],
        "text": message.get("transcript", ""),
        "final": bool(message.get("end_of_turn", False)),
    }


async def relay(browser: WebSocket, provider, sample_rate: int, conversation_id: str) -> None:
    """Run both directions concurrently; wait for the last turn after Stop."""
    termination_sent = False

    async def terminate() -> None:
        nonlocal termination_sent
        if not termination_sent:
            await provider.send(json.dumps({"type": "Terminate"}))
            termination_sent = True

    async def send_audio() -> None:
        while True:
            # A suspended tab or lost microphone must not leave a paid session open.
            try:
                message = await asyncio.wait_for(browser.receive(), timeout=20)
            except TimeoutError as exc:
                raise TranscriptionError("Audio stopped arriving. Please start again.") from exc
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(message.get("code", 1000))
            audio = message.get("bytes")
            if audio is not None:
                # 16-bit mono PCM; AssemblyAI accepts 20–1000 ms per chunk.
                if len(audio) % 2 or not sample_rate * 0.04 <= len(audio) <= sample_rate * 2:
                    raise TranscriptionError("Invalid audio chunk. Please restart recording.")
                await provider.send(audio)
            else:
                try:
                    control = json.loads(message.get("text", ""))
                except (TypeError, ValueError) as exc:
                    raise TranscriptionError("Invalid recording command.") from exc
                if control != {"type": "stop"}:
                    raise TranscriptionError("Unsupported recording command.")
                await terminate()
                return

    async def receive_transcripts() -> None:
        while True:
            message = json.loads(await provider.recv())
            if message.get("type") == "Turn":
                event = transcript_event(message)
                if event["final"] and event["text"].strip():
                    saved = await asyncio.to_thread(storage.append, conversation_id, event["turn_id"], "user", event["text"])
                    if not saved:
                        continue
                await browser.send_json(event)
            elif message.get("type") == "Termination":
                return
            elif message.get("type") == "Error":
                raise TranscriptionError("AssemblyAI reported an error. Check your account and try again.")

    sender = asyncio.create_task(send_audio())
    receiver = asyncio.create_task(receive_transcripts())
    try:
        done, _ = await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
        if sender in done:
            sender.result()  # A disconnect or malformed frame triggers cleanup below.
            try:
                await asyncio.wait_for(receiver, timeout=FINAL_TIMEOUT)
            except TimeoutError as exc:
                raise TranscriptionError("Final transcription timed out. The last turn may be incomplete.") from exc
        else:
            receiver.result()
        await asyncio.to_thread(storage.finish, conversation_id, "ended" if termination_sent else "interrupted")
        await browser.send_json({"type": "stopped"})
    finally:
        for task in (sender, receiver):
            if not task.done():
                task.cancel()
        await asyncio.gather(sender, receiver, return_exceptions=True)
        with suppress(Exception):
            await asyncio.wait_for(terminate(), timeout=2)


async def send_error(browser: WebSocket, message: str) -> None:
    with suppress(WebSocketDisconnect, RuntimeError, OSError):
        await browser.send_json({"type": "error", "message": message})


@router.websocket("/ws/transcribe")
async def transcribe(browser: WebSocket) -> None:
    # This local demo has no login. Reject other websites opening a paid session
    # through the user's browser; deployment beyond localhost needs authentication.
    origin = browser.headers.get("origin")
    if origin and urlsplit(origin).netloc != browser.headers.get("host"):
        await browser.close(code=1008)
        return

    await browser.accept()
    conversation_id = None
    try:
        api_key = os.environ.get("ASSEMBLYAI_API_KEY", "").strip()
        if not api_key:
            raise TranscriptionError("Transcription is not configured. Add your API key to .env and recreate the app container.")

        raw_start = await asyncio.wait_for(browser.receive_json(), timeout=START_TIMEOUT)
        start = StartMessage.model_validate(raw_start)
        if start.model not in MODELS:
            raise TranscriptionError("Choose a configured interview model.")
        model = os.environ.get("ASSEMBLYAI_SPEECH_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL

        # A bounded session also covers clients that stay connected indefinitely.
        async with asyncio.timeout(MAX_SESSION_SECONDS):
            async with connect(
                provider_url(start, model),
                additional_headers={"Authorization": api_key},
                open_timeout=START_TIMEOUT,
                close_timeout=2,
                max_size=1024 * 1024,
            ) as provider:
                relay_started = False
                try:
                    begin = json.loads(await asyncio.wait_for(provider.recv(), timeout=START_TIMEOUT))
                    if begin.get("type") != "Begin":
                        raise TranscriptionError("AssemblyAI could not start a transcription session.")
                    applied_model = begin.get("configuration", {}).get("model")
                    if applied_model and applied_model != model:
                        raise TranscriptionError("AssemblyAI selected an unexpected model. Check the configured speech model.")
                    conversation_id = await asyncio.to_thread(storage.start, start.language, start.tone, start.model, MODELS[start.model].provider)
                    await browser.send_json({"type": "ready", "conversation_id": conversation_id})
                    relay_started = True
                    await relay(browser, provider, start.sample_rate, conversation_id)
                finally:
                    # Covers disconnection during Begin/ready, before relay takes over.
                    if not relay_started:
                        with suppress(Exception):
                            await asyncio.wait_for(provider.send(json.dumps({"type": "Terminate"})), timeout=2)
    except WebSocketDisconnect:
        pass
    except ValidationError:
        await send_error(browser, "Choose German or English and a supported microphone sample rate.")
    except TranscriptionError as exc:
        await send_error(browser, str(exc))
    except InvalidStatus as exc:
        status = exc.response.status_code
        if status in (401, 403):
            message = "AssemblyAI rejected the connection. Check the API key and account access."
        elif status == 429:
            message = "AssemblyAI's session limit was reached. Please wait and try again."
        else:
            message = "AssemblyAI could not accept the connection. Check account access and model availability."
        await send_error(browser, message)
    except TimeoutError:
        await send_error(browser, "The session timed out or reached its 10-minute limit. Please start again.")
    except (ConnectionClosed, OSError):
        await send_error(browser, "The transcription connection was lost. Please start again.")
    except Exception as exc:
        # Avoid logging provider payloads, user audio/transcripts, or credentials.
        logger.warning("Transcription failure: %s", type(exc).__name__)
        await send_error(browser, "Transcription could not continue. Please try again.")
    finally:
        if conversation_id:
            await asyncio.to_thread(storage.finish, conversation_id, "interrupted")
        with suppress(WebSocketDisconnect, RuntimeError, OSError):
            await browser.close()
        if conversation_id:
            # The socket and STT session are closed before this extra model request.
            await summaries.after_close(conversation_id)
