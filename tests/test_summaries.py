import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi import Response

from app import storage, summaries
from app.main import history_detail


class SummaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict("os.environ", {"INTERVIEW_DB": str(Path(folder) / "demo.sqlite")}))
        storage.initialize()
        self.key = storage.start("de", "professional", "gpt-5.4-mini", "openai")
        self.model = AsyncMock()
        self.enterContext(patch.dict(summaries.PROVIDERS, {"openai": self.model}))
        result = dict.fromkeys(summaries.Summary.model_fields)
        result.update(overview="Ein Startup sucht Kapital.", financing_needs="500.000 Euro")
        self.model.reply.return_value = json.dumps(result)

    def saved(self):
        with storage.database() as db:
            return db.execute("SELECT * FROM summaries WHERE conversation_id=?", (self.key,)).fetchone()

    async def test_stop_saves_validated_record_once_and_history_reads_it_separately(self):
        storage.append(self.key, 0, "user", "Hallo")
        storage.append(self.key, 0, "assistant", "Was brauchen Sie?")
        storage.append(self.key, 1, "user", "500.000 Euro")
        await summaries.generate(self.key)
        self.model.reply.assert_not_awaited()
        storage.finish(self.key, "ended")
        await summaries.generate(self.key)
        await summaries.generate(self.key)
        self.model.reply.assert_awaited_once()
        _, instructions, messages = self.model.reply.call_args.args
        self.assertIn("German", instructions)
        self.assertEqual(json.loads(messages[0]["content"])[-1], {"speaker": "founder", "text": "500.000 Euro"})
        saved = self.saved()
        self.assertEqual(saved["source_last_position"], 3)
        self.assertEqual(saved["financing_needs"], "500.000 Euro")
        self.assertIsNone(saved["planned_round"])
        public = history_detail(UUID(self.key), Response())
        self.assertEqual(public["summary"]["overview"], saved["overview"])
        self.assertEqual(set(public["summary"]), set(summaries.Summary.model_fields))
        self.assertNotIn(saved["overview"], json.dumps(public["messages"]))
        self.model.reply.assert_awaited_once()
        self.assertEqual(len(public["messages"]), 3)

    async def test_empty_and_interrupted_interviews_skip_model(self):
        storage.finish(self.key, "ended")
        await summaries.generate(self.key)
        other = storage.start("en", "professional", "gpt-5.4-mini", "openai")
        storage.append(other, 0, "user", "Hello")
        storage.finish(other, "interrupted")
        await summaries.generate(other)
        self.model.reply.assert_not_awaited()

    async def test_invalid_output_or_provider_failure_leaves_transcript_available_for_retry(self):
        storage.append(self.key, 0, "user", "Final words")
        storage.finish(self.key, "ended")
        good = self.model.reply.return_value
        self.model.reply.side_effect = [RuntimeError("private error"), '{"overview":"private output"}', good]
        for _ in range(2):
            with self.assertLogs(summaries.logger.name, level="WARNING") as logs:
                await summaries.after_close(self.key)
            self.assertNotIn("private", str(logs.output))
            self.assertIsNone(self.saved())
        self.assertEqual(storage.snapshot(self.key)[1][0]["content"], "Final words")
        await summaries.generate(self.key)
        self.assertIsNotNone(self.saved())
