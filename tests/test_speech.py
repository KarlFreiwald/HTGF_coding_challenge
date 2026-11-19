"""Speech HTTP boundary, validation, and errors without consuming API credits."""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx2
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from app import speech

AsyncClient = httpx2.AsyncClient


class SpeechTests(unittest.IsolatedAsyncioTestCase):
    async def synthesize(self, handler, language="de", **env):
        def factory(**kwargs):
            self.assertEqual(kwargs["timeout"], 25.0)
            return AsyncClient(**kwargs, transport=httpx2.MockTransport(handler))
        with patch.dict("os.environ", {"ELEVENLABS_API_KEY": "test-only", "ELEVENLABS_VOICE_ID": speech.DEFAULT_VOICE,
                                       "ELEVENLABS_TTS_MODEL": speech.DEFAULT_MODEL} | env), \
             patch.object(speech.httpx2, "AsyncClient", side_effect=factory):
            return await speech.synthesize("Wie gross ist Ihr Team?", language)

    async def test_voice_language_format_auth_and_no_retries(self):
        for language in ("de", "en"):
            calls = []
            def handler(request):
                calls.append(request)
                self.assertEqual(request.url.path, "/v1/text-to-speech/anotherVoice")
                self.assertEqual(request.url.params["output_format"], "mp3_44100_128")
                self.assertEqual(request.headers["xi-api-key"], "test-only")
                self.assertEqual(json.loads(request.content), {
                    "text": "Wie gross ist Ihr Team?", "model_id": "eleven_flash_v2_5", "language_code": language,
                })
                return httpx2.Response(200, content=b"test-mp3", headers={"content-type": "audio/mpeg"})
            result = await self.synthesize(handler, language, ELEVENLABS_VOICE_ID="anotherVoice")
            self.assertEqual(result, b"test-mp3")
            self.assertEqual(len(calls), 1)

    async def test_missing_key_and_invalid_config_do_not_connect(self):
        for env in ({"ELEVENLABS_API_KEY": ""}, {"ELEVENLABS_VOICE_ID": "../invalid"}):
            with self.subTest(env=list(env)), self.assertRaises(HTTPException) as caught:
                await self.synthesize(lambda _: self.fail("Unexpected HTTP request"), **env)
            self.assertEqual(caught.exception.status_code, 503)

    async def test_provider_errors_are_sanitized_and_not_retried(self):
        for status, expected in [(401, 502), (403, 502), (429, 503), (500, 502)]:
            calls = []
            def handler(request):
                calls.append(request)
                return httpx2.Response(status, json={"detail": "private-provider-detail"})
            with self.subTest(status=status), self.assertRaises(HTTPException) as caught:
                await self.synthesize(handler)
            self.assertEqual(caught.exception.status_code, expected)
            self.assertNotIn("private-provider-detail", caught.exception.detail)
            self.assertEqual(len(calls), 1)

    async def test_empty_unexpected_or_oversized_audio_rejected(self):
        for content, mime in [(b"", "audio/mpeg"), (b"error", "application/json"), (b"x" * 5_000_001, "audio/mpeg")]:
            with self.subTest(size=len(content), mime=mime), self.assertRaises(HTTPException):
                await self.synthesize(lambda _: httpx2.Response(200, content=content, headers={"content-type": mime}))

    async def test_timeout_and_cancellation(self):
        def timeout(request):
            raise httpx2.ReadTimeout("private-detail", request=request)
        with self.assertRaises(HTTPException) as caught:
            await self.synthesize(timeout)
        self.assertEqual(caught.exception.status_code, 504)
        async def cancelled(_):
            raise asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.synthesize(cancelled)

    def test_input_bounds(self):
        for values in [{"text": ""}, {"text": " "}, {"text": "x" * 4001}, {"language": "fr"}, {"voice": "other"}]:
            with self.subTest(values=list(values)), self.assertRaises(ValidationError):
                speech.SpeechRequest(**({"text": "Hello", "language": "en"} | values))

    async def test_route_origin_and_audio_headers(self):
        body = speech.SpeechRequest(text="Hello", language="en")
        for origin, allowed in [("http://localhost:8000", True), ("https://other.example", False)]:
            request = Request({"type": "http", "headers": [(b"host", b"localhost:8000"), (b"origin", origin.encode())]})
            with patch.object(speech, "synthesize", AsyncMock(return_value=b"audio")) as synth:
                if allowed:
                    response = await speech.speech(body, request)
                    self.assertEqual(response.headers["content-type"], "audio/mpeg")
                    self.assertEqual(response.headers["cache-control"], "no-store")
                    self.assertEqual(response.body, b"audio")
                    synth.assert_awaited_once_with("Hello", "en")
                else:
                    with self.assertRaises(HTTPException) as caught:
                        await speech.speech(body, request)
                    self.assertEqual(caught.exception.status_code, 403)
                    synth.assert_not_called()
