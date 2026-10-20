import os
import time
from typing import Optional, Tuple
import cv2
import numpy as np

try:
    from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


class GuacamoleCapture:
    """
    Screen capture engine specialized for Apache Guacamole web client.
    Connects to the remote browser session over CDP (Chrome DevTools Protocol)
    or launches a dedicated Chromium instance.
    """

    def __init__(
        self,
        guacamole_url: Optional[str] = None,
        cdp_endpoint: str = "http://localhost:9222",
        headless: bool = False,
    ):
        self.guacamole_url = guacamole_url or os.getenv(
            "GUACAMOLE_URL",
            "http://localhost:60289/guacamole/#/client/UkRQIENvbm5lY3Rpb24AYwBkZWZhdWx0",
        )
        self.cdp_endpoint = cdp_endpoint
        self.headless = headless

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

        self.last_capture_time = 0.0
        self.fps = 0.0
        self.frame_count = 0

    @property
    def page(self) -> Optional[Page]:
        return self._page

    def connect(self) -> bool:
        """
        Connects to browser via CDP or launches a new browser instance.
        """
        if not HAS_PLAYWRIGHT:
            print("[GuacamoleCapture] Playwright not found in environment.", flush=True)
            return False

        self._playwright = sync_playwright().start()

        # 1. Try CDP connection to existing browser session
        try:
            print(f"[GuacamoleCapture] Connecting to CDP at {self.cdp_endpoint}...", flush=True)
            self._browser = self._playwright.chromium.connect_over_cdp(self.cdp_endpoint, timeout=3000)
            self._context = self._browser.contexts[0]

            # Find existing Guacamole page
            target_page = None
            for p in self._context.pages:
                if "guacamole" in p.url.lower():
                    target_page = p
                    break

            if target_page:
                self._page = target_page
                print(f"[GuacamoleCapture] Attached to existing Guacamole tab: {self._page.url}", flush=True)
            else:
                print(f"[GuacamoleCapture] Guacamole tab not open, navigating to {self.guacamole_url}...", flush=True)
                self._page = self._context.new_page()
                self._page.goto(self.guacamole_url, timeout=15000)

            self._page.bring_to_front()
            return True

        except Exception as cdp_err:
            print(f"[GuacamoleCapture] CDP not available ({cdp_err}). Launching standalone Chromium...", flush=True)

        # 2. Launch standalone browser
        try:
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=["--start-maximized", "--no-sandbox"],
            )
            self._context = self._browser.new_context(no_viewport=True)
            self._page = self._context.new_page()
            print(f"[GuacamoleCapture] Navigating to: {self.guacamole_url}", flush=True)
            self._page.goto(self.guacamole_url, timeout=20000)
            self._page.bring_to_front()
            return True
        except Exception as launch_err:
            print(f"[GuacamoleCapture Error] Failed to launch browser: {launch_err}", flush=True)
            return False

    def capture_frame(self) -> Optional[np.ndarray]:
        """
        Captures the current Guacamole viewport as an OpenCV BGR numpy array.
        """
        if self._page is None:
            return None

        t0 = time.time()
        try:
            screenshot_bytes = self._page.screenshot(type="jpeg", quality=85, timeout=2000)
            nparr = np.frombuffer(screenshot_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            now = time.time()
            dt = now - self.last_capture_time
            if dt > 0:
                instant_fps = 1.0 / dt
                self.fps = 0.9 * self.fps + 0.1 * instant_fps if self.fps > 0 else instant_fps
            self.last_capture_time = now
            self.frame_count += 1

            return frame
        except Exception as e:
            print(f"[GuacamoleCapture Warning] Frame capture error: {e}", flush=True)
            return None

    def get_viewport_size(self) -> Tuple[int, int]:
        """
        Returns (width, height) of the page viewport.
        """
        if self._page is not None:
            vp = self._page.viewport_size
            if vp:
                return vp["width"], vp["height"]
        return 1366, 768

    def close(self):
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception as e:
            print(f"[GuacamoleCapture] Close error: {e}", flush=True)
