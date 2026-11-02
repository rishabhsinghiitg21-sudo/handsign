"""The console can run shell commands, so a foreign web page must not reach it.

Run from the repo root:  .venv/bin/python -m unittest discover tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from handsign.server import app

OWN = "http://127.0.0.1:8000"
EVIL = "https://evil.example"


class OriginGuard(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app, base_url=OWN)

    def test_no_origin_allowed(self):
        self.assertEqual(self.c.get("/api/status").status_code, 200)

    def test_own_and_vite_origin_allowed(self):
        for o in (OWN, "http://localhost:8000", "http://localhost:5173"):
            self.assertEqual(self.c.get("/api/status", headers={"Origin": o}).status_code, 200)

    def test_foreign_origin_rejected_everywhere(self):
        h = {"Origin": EVIL}
        self.assertEqual(self.c.get("/api/status", headers=h).status_code, 403)
        self.assertEqual(self.c.put("/api/config", json={}, headers=h).status_code, 403)
        self.assertEqual(self.c.post("/api/workflow/x/trigger", headers=h).status_code, 403)
        self.assertEqual(self.c.get("/api/status", headers={"Origin": "null"}).status_code, 403)

    def test_rebinding_host_rejected(self):
        self.assertEqual(
            self.c.get("/api/status", headers={"Host": "evil.example:8000"}).status_code, 403)

    def test_cors_preflight_not_granted_to_foreign_origin(self):
        r = self.c.options("/api/config", headers={
            "Origin": EVIL, "Access-Control-Request-Method": "PUT"})
        self.assertNotIn("access-control-allow-origin", r.headers)
        self.assertEqual(r.status_code, 403)

    def test_websocket_foreign_origin_rejected(self):
        with self.assertRaises(WebSocketDisconnect):
            with self.c.websocket_connect("/ws/live", headers={"Origin": EVIL, "Host": "127.0.0.1:8000"}):
                pass

    def test_websocket_own_origin_accepted(self):
        with self.c.websocket_connect("/ws/live", headers={"Origin": OWN, "Host": "127.0.0.1:8000"}) as ws:
            self.assertIn("running", ws.receive_json())


if __name__ == "__main__":
    unittest.main()
