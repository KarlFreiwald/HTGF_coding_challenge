"""Exercise the real Google SDK over a fake HTTP transport; no paid calls."""

import asyncio
import json
import unittest
from unittest.mock import patch

import httpx2
from google import genai

from app import interview, llm

GoogleClient = genai.Client


class GeminiTests(unittest.IsolatedAsyncioTestCase):
    async def call_provider(self, handler, messages=None):
        def client_factory(**kwargs):
            options = kwargs["http_options"]
            self.assertEqual(options.retry_options.attempts, 1)
            self.assertEqual(options.timeout, 25000)
            options.async_client_args = {"transport": httpx2.MockTransport(handler)}
            return GoogleClient(**kwargs)

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-only"}), \
             patch.object(llm.genai, "Client", side_effect=client_factory):
            return await llm.GeminiProvider().reply(
                llm.MODELS["gemini-3.8-flash"], "Ask in German.",
                messages or [{"role": "user", "content": "We build robots."}],
            )

    async def test_real_sdk_serializes_history_and_parses_reply(self):
        requests = []

        def handler(request):
            requests.append(json.loads(request.content))
            return httpx2.Response(200, json={
                "id": "test-interaction", "status": "completed", "model": "gemini-3.8-flash",
                "steps": [{"type": "model_output", "content": [{"type": "text", "text": " Wie weit ist Ihr Produkt? "}]}],
            })

        result = await self.call_provider(handler, [
            {"role": "user", "content": "Wir bauen Roboter."},
            {"role": "assistant", "content": "Wie groß ist Ihr Team?"},
            {"role": "user", "content": "Fünf Personen."},
        ])
        self.assertEqual(result, "Wie weit ist Ihr Produkt?")
        self.assertEqual(len(requests), 1)
        body = requests[0]
        self.assertEqual(body["model"], "gemini-3.8-flash")
        self.assertEqual(body["system_instruction"], "Ask in German.")
        self.assertFalse(body["store"])
        self.assertNotIn("previous_interaction_id", body)
        self.assertEqual(body["generation_config"]["thinking_level"], "low")
        self.assertEqual([step["type"] for step in body["input"]], ["user_input", "model_output", "user_input"])
        self.assertEqual(body["input"][-1]["content"][0]["text"], "Fünf Personen.")

    async def test_missing_key_never_creates_sdk_client(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}), patch.object(llm.genai, "Client") as client:
            with self.assertRaises(llm.ReplyError) as caught:
                await llm.GeminiProvider().reply(llm.MODELS["gemini-3.8-flash"], "Instructions", [])
        self.assertEqual(caught.exception.status_code, 503)
        self.assertIn("GEMINI_API_KEY", str(caught.exception))
        client.assert_not_called()

    async def test_http_errors_sanitized_and_not_retried(self):
        for code, expected in [(400, "rejected the request"), (403, "rejected access"), (404, "unavailable"), (429, "quota or rate limit"), (503, "could not generate")]:
            requests = []

            def handler(request):
                requests.append(request)
                return httpx2.Response(code, json={"error": {"code": code, "message": "private-provider-detail"}})

            with self.subTest(code=code), self.assertRaises(llm.ReplyError) as caught:
                await self.call_provider(handler)
            self.assertIn(expected, str(caught.exception))
            self.assertNotIn("private-provider-detail", str(caught.exception))
            self.assertEqual(len(requests), 1)

    async def test_network_timeout_is_actionable(self):
        def handler(request):
            raise httpx2.ReadTimeout("private-detail", request=request)

        with self.assertRaises(llm.ReplyError) as caught:
            await self.call_provider(handler)
        self.assertEqual(caught.exception.status_code, 504)
        self.assertNotIn("private-detail", str(caught.exception))

    async def test_empty_or_incomplete_output_is_not_success_or_auto_continued(self):
        for status, text in [("completed", ""), ("failed", "Partial text"), ("requires_continuation", "Partial text")]:
            calls = []

            def handler(request):
                calls.append(request)
                return httpx2.Response(200, json={
                    "id": "test-interaction", "status": status, "continuation_token": "unused-token",
                    "steps": [{"type": "model_output", "content": [{"type": "text", "text": text}]}],
                })

            with self.subTest(status=status), self.assertRaises(llm.ReplyError):
                await self.call_provider(handler)
            self.assertEqual(len(calls), 1)

    async def test_cancellation_propagates(self):
        async def handler(request):
            raise asyncio.CancelledError()

        with self.assertRaises(asyncio.CancelledError):
            await self.call_provider(handler)

    async def test_catalog_and_request_validation_include_gemini(self):
        catalog = await interview.models()
        self.assertIn({"id": "gemini-3.8-flash", "label": "Gemini 3.8 Flash", "provider": "gemini"}, catalog["models"])
        request = interview.ReplyRequest(
            model="gemini-3.8-flash", language="de", tone="professional",
            messages=[{"role": "user", "content": "Hallo"}],
        )
        self.assertEqual(request.model, "gemini-3.8-flash")
