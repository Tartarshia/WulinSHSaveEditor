"""Track browser pages so the local editor exits after its last page closes."""
from __future__ import annotations

import threading
import time


class BrowserSessions:
    def __init__(self, close_grace: float = 4, heartbeat_timeout: float = 180, startup_timeout: float = 120, clock=time.monotonic):
        self.clock = clock
        self.started = clock()
        self.close_grace = close_grace
        self.heartbeat_timeout = heartbeat_timeout
        self.startup_timeout = startup_timeout
        self.pages: dict[str, float] = {}
        self.seen_page = False
        self.empty_since: float | None = None
        self.active_requests = 0
        self.stopping = False
        self.lock = threading.Lock()

    def heartbeat(self, page: str) -> bool:
        if not isinstance(page, str) or not 1 <= len(page) <= 100:
            raise ValueError("无效的页面会话。")
        with self.lock:
            if self.stopping:
                return False
            self.pages[page] = self.clock()
            self.seen_page = True
            self.empty_since = None
            return True

    def close(self, page: str) -> None:
        with self.lock:
            if page in self.pages:
                del self.pages[page]
                if not self.pages:
                    self.empty_since = self.clock()

    def begin_request(self) -> bool:
        with self.lock:
            if self.stopping:
                return False
            self.active_requests += 1
            return True

    def end_request(self) -> None:
        with self.lock:
            self.active_requests -= 1

    def should_stop(self) -> bool:
        with self.lock:
            now = self.clock()
            expired = [page for page, last in self.pages.items() if now - last >= self.heartbeat_timeout]
            for page in expired:
                del self.pages[page]
            if expired and not self.pages and self.empty_since is None:
                self.empty_since = now
            idle = (self.seen_page and not self.pages and self.empty_since is not None and now - self.empty_since >= self.close_grace)
            unattended = not self.seen_page and now - self.started >= self.startup_timeout
            if not self.active_requests and (idle or unattended):
                self.stopping = True
                return True
            return False
