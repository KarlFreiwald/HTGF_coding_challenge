import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx2

from app import storage
from app.main import app


class HistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_archive_survives_restart_and_excludes_active_interviews(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict("os.environ", {"INTERVIEW_DB": str(Path(folder) / "history.sqlite")}))
        client = await self.enterAsyncContext(httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://localhost",
        ))
        async with app.router.lifespan_context(app):
            self.assertEqual((await client.get("/api/history")).json(), [])
            ended = storage.start("de", "professional", "m1", "example")
            storage.append(ended, 0, "user", "Hallo")
            storage.append(ended, 0, "assistant", "Wie weit sind Sie?")
            storage.finish(ended, "ended")
            interrupted = storage.start("en", "conversational", "m2", "example")
            storage.append(interrupted, 0, "user", "Unanswered turn")

        async with app.router.lifespan_context(app):
            active = storage.start("de", "professional", "m1", "example")
            listing = await client.get("/api/history")
            self.assertEqual([r["id"] for r in listing.json()], [interrupted, ended])
            self.assertEqual(listing.headers["cache-control"], "no-store")
            for key in [active, uuid4()]:
                self.assertEqual((await client.get(f"/api/history/{key}")).status_code, 404)
            result = (await client.get(f"/api/history/{ended}")).json()
            self.assertEqual([(m["role"], m["content"]) for m in result["messages"]],
                             [("user", "Hallo"), ("assistant", "Wie weit sind Sie?")])
            self.assertEqual(result["conversation"]["tone"], "professional")
            self.assertIsNotNone(result["conversation"]["ended_at"])
            saved = (await client.get(f"/api/history/{interrupted}")).json()
            self.assertEqual(saved["conversation"]["status"], "interrupted")
            self.assertEqual(saved["messages"][0]["content"], "Unanswered turn")
            self.assertEqual((await client.post(f"/api/history/{ended}")).status_code, 405)
