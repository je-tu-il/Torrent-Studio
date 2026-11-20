# -*- coding: utf-8 -*-
import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from torrent_manager import DEFAULT_TRACKERS
from app import app
from fastapi.testclient import TestClient

class TestTorrentStudio(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_default_trackers(self):
        self.assertGreater(len(DEFAULT_TRACKERS), 0)
        self.assertTrue(any("openbittorrent" in t for t in DEFAULT_TRACKERS))

    def test_quick_folders(self):
        response = self.client.get("/api/quick-folders")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("folders", data)
        self.assertIsInstance(data["folders"], list)

    def test_index_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))

if __name__ == "__main__":
    unittest.main()
