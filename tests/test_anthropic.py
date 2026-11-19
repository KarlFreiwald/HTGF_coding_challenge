"""Real Anthropic SDK over a fake HTTP transport; no credits consumed."""

import asyncio
import json
import unittest
from unittest.mock import patch

import anthropic
import httpx2

from app import interview, llm

AsyncAnthropic = anthropic.AsyncAnthropic


class AnthropicTests(unittest.IsolatedAsyncioTestCase):
    async def call_provider(self, handler):
        def client_factory(**kwargs):
            self.assertEqual(kwargs["max_retries"], 0)
            self.assertEqual(kwargs["timeout"], 25.0)
            return AsyncAnthropic(**kwargs, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)))

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-only"}), \
             patch.object(llm.anthropic, "AsyncAnthropic", side_effect=client_factory):
            return await llm.AnthropicProvider().reply(
                llm.MODELS["claude-haiku-5-5"], "Ask in German using Sie.", [
                    {"role": "user", "content": "Wir bauen Roboter."},
                    {"role": "assistant", "content": "Wie groß ist Ihr Team?"},
                    {"role": "user", "content": "Fünf Personen."},
                ],
            )

    @staticmethod
    def response(content, stop_reason="end_turn"):
        return httpx2.Response(200, json={
            "id": "msg_test", "type": "message", "role": "assistant",
            "model": "claude-haiku-5-5", "content": content,
            "stop_reason": stop_reason, "stop_sequence": None,
            "usage": {"input_tokens": 80, "output_tokens": 20},
        })

    async def test_sdk_preserves_history_and_uses_budget_settings(self):
        requests = []

        def handler(request):
            requests.append(json.loads(request.content))
            return self.response([
                {"type": "text", "text": "Danke."},
                {"type": "text", "text": "Wie weit ist Ihr Produkt?"},
            ])

        result = await self.call_provider(handler)
        self.assertEqual(result, "Danke.\nWie weit ist Ihr Produkt?")
        self.assertEqual(len(requests), 1)
        body = requests[0]
        self.assertEqual(body["model"], "claude-haiku-5-5")
        self.assertEqual(body["system"], "Ask in German using Sie.")
        self.assertEqual([message["role"] for message in body["messages"]], ["user", "assistant", "user"])
        self.assertEqual(body["messages"][-1]["content"], "Fünf Personen.")
        self.assertEqual(body["max_tokens"], 500)
        self.assertEqual(body["thinking"], {"type": "disabled"})
        self.assertEqual(body["output_config"], {"effort": "low"})
        self.assertNotIn("store", body)

    async def test_missing_key_never_creates_client(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}), patch.object(llm.anthropic, "AsyncAnthropic") as client:
            with self.assertRaises(llm.ReplyError) as caught:
                await llm.AnthropicProvider().reply(llm.MODELS["claude-haiku-5-5"], "Instructions", [])
        self.assertEqual(caught.exception.status_code, 503)
        self.assertIn("ANTHROPIC_API_KEY", str(caught.exception))
        client.assert_not_called()

    async def test_errors_are_sanitized_and_never_retried(self):
        for code, expected in [(400, "rejected the request"), (401, "rejected access"), (403, "rejected access"), (404, "unavailable"), (429, "quota or rate limit"), (529, "could not generate")]:
            calls = []

            def handler(request):
                calls.append(request)
                return httpx2.Response(code, json={"type": "error", "error": {"type": "api_error", "message": "private-provider-detail"}})

            with self.subTest(code=code), self.assertRaises(llm.ReplyError) as caught:
                await self.call_provider(handler)
            self.assertIn(expected, str(caught.exception))
            self.assertNotIn("private-provider-detail", str(caught.exception))
            self.assertEqual(len(calls), 1)

    async def test_timeout_is_actionable(self):
        def handler(request):
            raise httpx2.ReadTimeout("private-detail", request=request)

        with self.assertRaises(llm.ReplyError) as caught:
            await self.call_provider(handler)
        self.assertEqual(caught.exception.status_code, 504)

    async def test_truncation_refusal_and_empty_text_are_not_success(self):
        for reason, content in [
            ("max_tokens", [{"type": "text", "text": "Partial answer"}]),
            ("refusal", [{"type": "text", "text": "Declined"}]),
            ("end_turn", []),
            ("end_turn", [{"type": "thinking", "thinking": "Not a reply", "signature": "test"}]),
        ]:
            with self.subTest(reason=reason), self.assertRaises(llm.ReplyError):
                await self.call_provider(lambda request: self.response(content, reason))

    async def test_cancellation_propagates(self):
        async def handler(request):
            raise asyncio.CancelledError()

        with self.assertRaises(asyncio.CancelledError):
            await self.call_provider(handler)

    async def test_haiku_is_default_and_other_providers_remain_available(self):
        catalog = await interview.models()
        self.assertEqual(catalog["default"], "claude-haiku-5-5")
        self.assertEqual({item["provider"] for item in catalog["models"]}, {"anthropic", "gemini", "openai"})
        self.assertEqual(len(catalog["models"]), 4)
        request = interview.ReplyRequest(
            model="claude-haiku-5-5", language="de", tone="professional",
            messages=[{"role": "user", "content": "Hallo"}],
        )
        self.assertEqual(request.model, "claude-haiku-5-5")
