"""Lifecycle tests with a simulated provider: no API key or paid calls needed."""

import asyncio
import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

from app import transcription as stt


class Browser:
    def __init__(self, language="de", sample_rate=48000, origin="http://localhost:8000"):
        self.headers = {"host": "localhost:8000", "origin": origin}
        self.incoming = asyncio.Queue()
        self.outgoing = asyncio.Queue()
        self.events = []
        self.start = {"type": "start", "language": language, "sample_rate": sample_rate}
        self.closed = False
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def close(self, code=1000):
        self.closed = True

    async def receive_json(self):
        return self.start

    async def receive(self):
        return await self.incoming.get()

    async def send_json(self, event):
        self.events.append(event)
        await self.outgoing.put(event)

    async def next_event(self):
        return await asyncio.wait_for(self.outgoing.get(), timeout=2)


class Provider:
    def __init__(self, finish=True, model=stt.DEFAULT_MODEL):
        self.incoming = asyncio.Queue()
        self.incoming.put_nowait(json.dumps({"type": "Begin", "configuration": {"model": model}}))
        self.sent = []
        self.finish = finish
        self.closed = False

    async def recv(self):
        return await self.incoming.get()

    async def send(self, frame):
        self.sent.append(frame)
        if isinstance(frame, bytes):
            self.incoming.put_nowait(json.dumps({
                "type": "Turn", "turn_order": 0, "transcript": "Wir suchen", "end_of_turn": False,
            }))
        elif json.loads(frame)["type"] == "Terminate" and self.finish:
            self.incoming.put_nowait(json.dumps({
                "type": "Turn", "turn_order": 0,
                "transcript": "Wir suchen 500.000 Euro.", "end_of_turn": True,
            }))
            self.incoming.put_nowait(json.dumps({"type": "Termination"}))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True


class TranscriptionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict("os.environ", {"INTERVIEW_DB": str(Path(folder) / "demo.sqlite")}))
        stt.storage.initialize()
        self.summarize = self.enterContext(patch.object(stt.summaries, "after_close", new_callable=AsyncMock))

    async def run_session(self, browser, provider, interaction):
        with patch.dict("os.environ", {"ASSEMBLYAI_API_KEY": "test-secret", "ASSEMBLYAI_SPEECH_MODEL": stt.DEFAULT_MODEL}), \
             patch.object(stt, "connect", return_value=provider) as connection:
            task = asyncio.create_task(stt.transcribe(browser))
            try:
                await interaction(browser)
                await asyncio.wait_for(task, timeout=2)
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(browser.closed)
        self.assertTrue(provider.closed)
        return connection

    async def test_final_transcript_arrives_before_stopped_and_audio_is_unchanged(self):
        browser, provider = Browser(sample_rate=44100), Provider()
        audio = b"\x01\x00" * 4410

        async def interaction(client):
            self.assertEqual((await client.next_event())["type"], "ready")
            await client.incoming.put({"type": "websocket.receive", "bytes": audio})
            partial = await client.next_event()
            self.assertFalse(partial["final"])
            await client.incoming.put({"type": "websocket.receive", "text": '{"type":"stop"}'})

        connection = await self.run_session(browser, provider, interaction)
        self.assertEqual(provider.sent[0], audio)
        self.assertEqual(sum(isinstance(frame, str) for frame in provider.sent), 1)
        self.assertTrue(browser.events[-2]["final"])
        self.assertEqual(browser.events[-1], {"type": "stopped"})
        settings, history = stt.storage.snapshot(browser.events[0]["conversation_id"])
        self.assertEqual(settings["status"], "ended")
        self.summarize.assert_awaited_once_with(browser.events[0]["conversation_id"])
        self.assertEqual([m["content"] for m in history], ["Wir suchen 500.000 Euro."])
        query = parse_qs(urlsplit(connection.call_args.args[0]).query)
        self.assertEqual(query["sample_rate"], ["44100"])
        self.assertEqual(json.loads(query["language_codes"][0]), ["de"])
        self.assertNotIn("test-secret", connection.call_args.args[0])
        self.assertNotIn("test-secret", json.dumps(browser.events))

    async def test_disconnect_terminates_the_provider(self):
        browser, provider = Browser(language="en"), Provider()

        async def interaction(client):
            await client.next_event()
            await client.incoming.put({"type": "websocket.disconnect", "code": 1001})

        connection = await self.run_session(browser, provider, interaction)
        self.assertEqual(json.loads(provider.sent[-1]), {"type": "Terminate"})
        self.assertEqual(stt.storage.snapshot(browser.events[0]["conversation_id"])[0]["status"], "interrupted")
        query = parse_qs(urlsplit(connection.call_args.args[0]).query)
        self.assertEqual(json.loads(query["language_codes"][0]), ["en"])

    async def test_missing_key_does_not_contact_provider(self):
        browser = Browser()
        with patch.dict("os.environ", {"ASSEMBLYAI_API_KEY": ""}), patch.object(stt, "connect") as connection:
            await stt.transcribe(browser)
        connection.assert_not_called()
        self.assertEqual(browser.events[0]["type"], "error")

    async def test_invalid_language_does_not_open_paid_session(self):
        browser = Browser(language="fr")
        with patch.dict("os.environ", {"ASSEMBLYAI_API_KEY": "test"}), patch.object(stt, "connect") as connection:
            await stt.transcribe(browser)
        connection.assert_not_called()
        self.assertEqual(browser.events[0]["type"], "error")

    async def test_other_website_origin_is_rejected(self):
        browser = Browser(origin="https://another-site.example")
        with patch.object(stt, "connect") as connection:
            await stt.transcribe(browser)
        connection.assert_not_called()
        self.assertFalse(browser.accepted)
        self.assertTrue(browser.closed)

    async def test_bad_audio_closes_both_sides(self):
        browser, provider = Browser(), Provider()

        async def interaction(client):
            await client.next_event()
            await client.incoming.put({"type": "websocket.receive", "bytes": b"odd"})

        await self.run_session(browser, provider, interaction)
        self.assertEqual(browser.events[-1]["type"], "error")
        self.assertEqual(json.loads(provider.sent[-1]), {"type": "Terminate"})

    async def test_provider_error_is_sanitized_and_session_closed(self):
        browser, provider = Browser(), Provider()

        async def interaction(client):
            await client.next_event()
            provider.incoming.put_nowait(json.dumps({"type": "Error", "message": "private payload"}))

        await self.run_session(browser, provider, interaction)
        self.assertEqual(browser.events[-1]["type"], "error")
        self.assertNotIn("private payload", json.dumps(browser.events))

    async def test_stop_timeout_is_bounded_and_does_not_claim_success(self):
        browser, provider = Browser(), Provider(finish=False)

        async def interaction(client):
            await client.next_event()
            await client.incoming.put({"type": "websocket.receive", "text": '{"type":"stop"}'})

        with patch.object(stt, "FINAL_TIMEOUT", 0.03):
            await self.run_session(browser, provider, interaction)
        self.assertEqual(browser.events[-1]["type"], "error")
        self.assertIn("incomplete", browser.events[-1]["message"])

    async def test_unexpected_provider_model_is_closed_before_audio(self):
        browser, provider = Browser(), Provider(model="unexpected")

        async def interaction(client):
            self.assertEqual((await client.next_event())["type"], "error")

        await self.run_session(browser, provider, interaction)
        self.assertEqual(json.loads(provider.sent[-1]), {"type": "Terminate"})


if __name__ == "__main__":
    unittest.main()
