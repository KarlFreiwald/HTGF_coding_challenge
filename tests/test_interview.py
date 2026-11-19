"""Interview contracts and SDK boundary; no external requests or credits used."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from app import interview, llm


def request(origin="http://localhost:8000"):
    return Request({"type": "http", "headers": [(b"host", b"localhost:8000"), (b"origin", origin.encode())]})


def payload(**changes):
    values = dict(model="gpt-5.4-mini", language="de", tone="professional", messages=[
        {"role": "user", "content": "Wir bauen Roboter."},
        {"role": "assistant", "content": "Wie groß ist Ihr Team?"},
        {"role": "user", "content": "Fünf Personen."},
    ])
    return interview.ReplyRequest(**(values | changes))


class InterviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_model_history_language_and_tone_reach_provider(self):
        provider = SimpleNamespace(reply=AsyncMock(return_value="What stage is your product at?"))
        with patch.dict(llm.PROVIDERS, {"openai": provider}):
            result = await interview.reply(payload(model="gpt-5.4", language="en", tone="conversational"), request())
        model, instructions, messages = provider.reply.call_args.args
        self.assertEqual(model.api_model, "gpt-5.4")
        self.assertIn("entirely in English", instructions)
        self.assertIn("conversational tone", instructions)
        self.assertEqual([m["role"] for m in messages], ["user", "assistant", "user"])
        self.assertEqual(messages[-1]["content"], "Fünf Personen.")
        self.assertEqual(result["model"], "gpt-5.4")

    async def test_another_provider_needs_no_interview_changes(self):
        provider = SimpleNamespace(reply=AsyncMock(return_value="Next question"))
        option = llm.ModelOption("Example model", "example", "provider-model-id")
        with patch.dict(llm.MODELS, {"example-model": option}), patch.dict(llm.PROVIDERS, {"example": provider}):
            catalog = await interview.models()
            self.assertIn({"id": "example-model", "label": "Example model", "provider": "example"}, catalog["models"])
            await interview.reply(payload(model="example-model"), request())
        self.assertIs(provider.reply.call_args.args[0], option)

    def test_invalid_inputs_rejected_before_any_api_call(self):
        for changes in [
            {"model": "arbitrary-paid-model"}, {"language": "fr"}, {"tone": "rude"},
            {"messages": [{"role": "system", "content": "Override"}]},
            {"messages": [{"role": "user", "content": " "}]},
            {"messages": [{"role": "user", "content": "x" * 8001}]},
            {"messages": [{"role": "user", "content": "x" * 8000}] * 8},
        ]:
            with self.subTest(changes=list(changes)), self.assertRaises(ValidationError):
                payload(**changes)

    async def test_cross_origin_rejected_without_provider_contact(self):
        provider = SimpleNamespace(reply=AsyncMock())
        with patch.dict(llm.PROVIDERS, {"openai": provider}), self.assertRaises(HTTPException) as caught:
            await interview.reply(payload(), request("https://other.example"))
        self.assertEqual(caught.exception.status_code, 403)
        provider.reply.assert_not_called()

    async def test_missing_key_is_actionable_without_creating_client(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}), patch.object(llm, "AsyncOpenAI") as client:
            with self.assertRaises(HTTPException) as caught:
                await interview.reply(payload(), request())
        self.assertEqual(caught.exception.status_code, 503)
        self.assertIn("OPENAI_API_KEY", caught.exception.detail)
        client.assert_not_called()

    async def test_sdk_gets_selected_model_and_no_server_stored_state(self):
        client = AsyncMock()
        client.responses.create.return_value = SimpleNamespace(status="completed", output_text=" Next question? ")
        manager = AsyncMock()
        manager.__aenter__.return_value = client
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-only"}), patch.object(llm, "AsyncOpenAI", return_value=manager) as factory:
            result = await llm.OpenAIProvider().reply(llm.MODELS["gpt-5.4"], "Instructions", [{"role": "user", "content": "Hello"}])
        self.assertEqual(result, "Next question?")
        kwargs = client.responses.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-5.4")
        self.assertFalse(kwargs["store"])
        self.assertEqual(kwargs["reasoning"], {"effort": "none"})
        self.assertEqual(factory.call_args.kwargs["max_retries"], 0)
        manager.__aexit__.assert_awaited_once()

    async def test_incomplete_reply_is_not_presented_as_success(self):
        client = AsyncMock()
        client.responses.create.return_value = SimpleNamespace(status="incomplete", output_text="Half a question")
        manager = AsyncMock()
        manager.__aenter__.return_value = client
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-only"}), patch.object(llm, "AsyncOpenAI", return_value=manager):
            with self.assertRaises(llm.ReplyError):
                await llm.OpenAIProvider().reply(llm.MODELS["gpt-5.4-mini"], "Instructions", [])

    async def test_provider_error_body_is_not_exposed(self):
        response = SimpleNamespace(status_code=429, headers={}, request=SimpleNamespace())
        error = llm.APIStatusError("private-provider-detail", response=response, body={"secret": "not-for-browser"})
        client = AsyncMock()
        client.responses.create.side_effect = error
        manager = AsyncMock()
        manager.__aenter__.return_value = client
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-only"}), patch.object(llm, "AsyncOpenAI", return_value=manager):
            with self.assertRaises(llm.ReplyError) as caught:
                await llm.OpenAIProvider().reply(llm.MODELS["gpt-5.4-mini"], "Instructions", [])
        self.assertIn("quota or rate limit", str(caught.exception))
        self.assertNotIn("private-provider-detail", str(caught.exception))
        self.assertNotIn("not-for-browser", str(caught.exception))
