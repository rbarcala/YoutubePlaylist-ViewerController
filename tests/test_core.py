"""Pruebas unitarias para los componentes en core/."""
import unittest
import queue
import tempfile
import shutil
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from core.websocket_manager import WebSocketManager
from core.video_manager import VideoManager


class TestWebSocketManager(unittest.TestCase):
    """Pruebas para WebSocketManager."""

    def setUp(self):
        self.ws = WebSocketManager()

    def test_add_remove_listener(self):
        q = queue.Queue()
        self.ws.add_listener(q)
        self.assertIn(q, self.ws.listeners)
        self.ws.remove_listener(q)
        self.assertNotIn(q, self.ws.listeners)

    def test_broadcast_event_formatting(self):
        q = queue.Queue()
        self.ws.add_listener(q)
        self.ws.broadcast_event("test_event", {"hello": "world"})
        self.assertFalse(q.empty())
        msg = q.get_nowait()
        self.assertTrue(msg.startswith("event: test_event\n"))
        self.assertIn('"data": {"hello": "world"}', msg)
        self.assertIn('"type": "test_event"', msg)


class TestVideoManager(unittest.TestCase):
    """Pruebas para VideoManager."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.video_mgr = VideoManager(Path(self.temp_dir))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cached_path_not_found(self):
        self.assertIsNone(self.video_mgr.get_cached_path("non_existent_id"))

    def test_cached_path_found(self):
        test_file = Path(self.temp_dir) / "test1234.mp4"
        test_file.write_text("dummy video")
        cached = self.video_mgr.get_cached_path("test1234")
        self.assertIsNotNone(cached)
        self.assertEqual(cached.name, "test1234.mp4")

    def test_cached_path_ignores_part(self):
        part_file = Path(self.temp_dir) / "test5678.mp4.part"
        part_file.write_text("in progress")
        self.assertIsNone(self.video_mgr.get_cached_path("test5678"))


if __name__ == '__main__':
    unittest.main()

