import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from app import interview, storage
from app.llm import ReplyError


class SavedInterviewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict("os.environ", {"INTERVIEW_DB": str(Path(folder) / "test.sqlite")}))
        storage.initialize()
        self.key = storage.start("de", "professional", "gpt-5.4-mini", "openai")
        self.provider = SimpleNamespace(reply=AsyncMock(return_value="Wie gross ist Ihr Team?"))
        self.enterContext(patch.dict(interview.PROVIDERS, {"openai": self.provider}))
        self.request = SimpleNamespace(headers={}, is_disconnected=AsyncMock(return_value=False))

    async def reply(self, turn):
        return await interview.saved_reply(interview.SavedTurn(conversation_id=self.key, turn_id=turn), self.request)

    async def test_model_failure_survives_restart_and_duplicate_final(self):
        storage.append(self.key, 0, "user", "Wir bauen Roboter.")
        self.assertFalse(storage.append(self.key, 0, "user", "Wir bauen Roboter."))
        self.provider.reply.side_effect = ReplyError("Provider unavailable", 503)
        with self.assertRaises(HTTPException):
            await self.reply(0)
        storage.initialize()
        settings, history = storage.snapshot(self.key)
        self.assertEqual(settings["status"], "interrupted")
        self.assertEqual([m["content"] for m in history], ["Wir bauen Roboter."])

    async def test_reply_uses_saved_history_and_replay_is_idempotent(self):
        storage.append(self.key, 0, "user", "Wir bauen Roboter.")
        first = await self.reply(0)
        self.assertEqual(first, await self.reply(0))
        self.provider.reply.assert_awaited_once()
        storage.append(self.key, 1, "user", "Drei Personen.")
        await self.reply(1)
        model, instructions, messages = self.provider.reply.call_args.args
        self.assertEqual(model.api_model, "gpt-5.4-mini")
        self.assertIn("Sie", instructions)
        self.assertEqual([m["content"] for m in messages], ["Wir bauen Roboter.", first["text"], "Drei Personen."])

    async def test_new_turn_or_stop_while_waiting_discards_obsolete_reply(self):
        storage.append(self.key, 0, "user", "First turn")
        async def more_speech(*args):
            storage.append(self.key, 1, "user", "New detail")
            return "Obsolete question"
        self.provider.reply.side_effect = more_speech
        self.assertEqual(await self.reply(0), {"superseded": True})
        async def stopped(*args):
            storage.finish(self.key, "ended")
            return "Late question"
        self.provider.reply.side_effect = stopped
        self.assertEqual(await self.reply(1), {"superseded": True})
        self.assertEqual(len(storage.snapshot(self.key)[1]), 2)
