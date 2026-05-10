import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import backend.main as app_main


class MainApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_config_dir = app_main.CONFIG_DIR
        self._old_config_file = app_main.CONFIG_FILE
        app_main.CONFIG_DIR = Path(self._tmp.name)
        app_main.CONFIG_FILE = app_main.CONFIG_DIR / "settings.json"
        self.client = TestClient(app_main.app)

    def tearDown(self):
        app_main.CONFIG_DIR = self._old_config_dir
        app_main.CONFIG_FILE = self._old_config_file
        self._tmp.cleanup()

    def test_settings_never_returns_api_key(self):
        resp = self.client.post("/api/settings", json={
            "api_key": "test-secret-value",
            "base_url": "https://api.example.com",
            "api_format": "openai",
            "model": "",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["has_api_key"])
        self.assertNotIn("api_key", data)

        resp = self.client.get("/api/settings")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["has_api_key"])
        self.assertNotIn("api_key", data)

    def test_health(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])


if __name__ == "__main__":
    unittest.main()
