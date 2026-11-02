"""PUT /api/config must validate, and must never leave a half-written gestures.json.

Run from the repo root:  .venv/bin/python -m unittest discover tests
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.testclient import TestClient

from handsign import server
from handsign.fsutil import atomic_write_text

OWN = "http://127.0.0.1:8000"


class ConfigApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "gestures.json"
        self.path.write_text('{"poses": {}}')
        patcher = mock.patch.object(server, "CONFIG_PATH", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        self.c = TestClient(server.app, base_url=OWN)

    def test_valid_config_is_saved(self):
        cfg = {"poses": {"fist": {"action": {"type": "key", "value": "esc"}}}}
        self.assertEqual(self.c.put("/api/config", json=cfg).status_code, 200)
        self.assertEqual(json.loads(self.path.read_text()), cfg)
        self.assertEqual(self.c.get("/api/config").json(), cfg)

    def test_invalid_config_is_rejected_and_file_untouched(self):
        before = self.path.read_text()
        for bad in ({"poses": "nope"},
                    {"poses": {"fist": {"action": "esc"}}},
                    {"workflows": {"w": {"steps": [{"action": {"type": "key"}, "delay_ms": "x"}]}}},
                    {"sequences": []}):
            r = self.c.put("/api/config", json=bad)
            self.assertEqual(r.status_code, 400, bad)
        self.assertEqual(self.c.put("/api/config", json=[1, 2]).status_code, 422)
        self.assertEqual(self.path.read_text(), before)
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["gestures.json"])

    def test_atomic_write_leaves_old_file_if_writing_fails(self):
        atomic_write_text(self.path, "old")
        with mock.patch("handsign.fsutil.os.replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                atomic_write_text(self.path, "new")
        self.assertEqual(self.path.read_text(), "old")
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["gestures.json"])

    def test_samples_for_builtin_pose_is_empty_not_404(self):
        with mock.patch.object(server, "DATASET_PATH", Path(self.tmp.name) / "none.json"):
            r = self.c.get("/api/dataset/fist/samples")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["medoid"])


if __name__ == "__main__":
    unittest.main()
