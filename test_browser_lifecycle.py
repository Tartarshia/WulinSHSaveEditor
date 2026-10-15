"""Lifecycle tests use synthetic pages and never load or write game saves."""
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import unittest
from urllib.request import Request, urlopen

from browser_lifecycle import BrowserSessions


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.sessions = BrowserSessions(clock=lambda: self.now)

    def test_refresh_and_multiple_pages(self):
        self.sessions.heartbeat("a")
        self.sessions.heartbeat("b")
        self.sessions.close("a")
        self.now = 10
        self.assertFalse(self.sessions.should_stop())
        self.sessions.close("b")
        self.now = 12
        self.sessions.heartbeat("refreshed")
        self.now = 15
        self.assertFalse(self.sessions.should_stop())
        self.sessions.close("refreshed")
        self.now = 19
        self.assertTrue(self.sessions.should_stop())

    def test_waits_for_save_request(self):
        self.sessions.heartbeat("a")
        self.assertTrue(self.sessions.begin_request())
        self.sessions.close("a")
        self.now = 20
        self.assertFalse(self.sessions.should_stop())
        self.sessions.end_request()
        self.assertTrue(self.sessions.should_stop())
        self.assertFalse(self.sessions.begin_request())

    def test_crash_and_unopened_browser(self):
        self.sessions.heartbeat("crashed")
        self.now = 181
        self.assertFalse(self.sessions.should_stop())
        self.now = 185
        self.assertTrue(self.sessions.should_stop())
        other = BrowserSessions(clock=lambda: self.now)
        self.now += 120
        self.assertTrue(other.should_stop())

    def test_invalid_close_token_is_rejected(self):
        from web_app import make_app
        app = make_app(18765, self.sessions)
        with app.test_client() as client:
            self.sessions.heartbeat("a")
            self.assertEqual(client.post("/api/session/close", json={"page": "a", "token": "wrong"}).status_code, 403)
            self.assertIn("a", self.sessions.pages)
            self.assertEqual(self.sessions.active_requests, 0)


class ServerTests(unittest.TestCase):
    def test_server_exits_and_releases_port_after_last_page(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        root = Path(__file__).resolve().parent
        command = [sys.executable, str(root / "web_app.py"), "--port", str(port), "--no-browser"]
        proc = subprocess.Popen(command, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f"http://127.0.0.1:{port}"
        try:
            deadline = time.monotonic() + 15
            while True:
                try:
                    with urlopen(base + "/", timeout=1) as response:
                        page = response.read().decode()
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        self.fail("Test server did not start")
                    time.sleep(0.1)
            token = re.search(r'name="wulin-token" content="([^"]+)"', page).group(1)
            def post(route, payload, beacon=False):
                payload = dict(payload)
                headers = {"Content-Type": "application/json", "Origin": base}
                if beacon:
                    payload["token"] = token
                else:
                    headers["X-Wulin-Token"] = token
                with urlopen(Request(base + route, data=json.dumps(payload).encode(), headers=headers), timeout=3) as response:
                    return json.load(response)
            for key in ("a", "b"):
                post("/api/session/heartbeat", {"page": key})
            duplicate = subprocess.run(command, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            self.assertEqual(duplicate.returncode, 0)
            post("/api/session/close", {"page": "a"}, beacon=True)
            time.sleep(4.7)
            self.assertIsNone(proc.poll(), "Other open page must keep the server alive")
            post("/api/session/close", {"page": "b"}, beacon=True)
            post("/api/session/heartbeat", {"page": "refresh"})
            post("/api/session/close", {"page": "refresh"}, beacon=True)
            self.assertEqual(proc.wait(timeout=10), 0)
            with socket.socket() as sock:
                self.assertNotEqual(sock.connect_ex(("127.0.0.1", port)), 0)
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
