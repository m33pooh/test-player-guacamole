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
        username: Optional[str] = None,
        password: Optional[str] = None,
        user_data_dir: Optional[str] = None,
    ):
        self.guacamole_url = guacamole_url or os.getenv(
            "GUACAMOLE_URL",
            "http://localhost:8080/guacamole/#/client/UkRQIENvbm5lY3Rpb24AYwBkZWZhdWx0",
        )
        self.cdp_endpoint = cdp_endpoint
        self.headless = headless
        self.username = username or os.getenv("GUACAMOLE_USER")
        self.password = password or os.getenv("GUACAMOLE_PASS")
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        default_session_dir = os.path.join(base_dir, "data", "browser_session")
        self.user_data_dir = user_data_dir or default_session_dir

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

        self._game_crop_bounds: Optional[Tuple[int, int, int, int]] = None
        self.last_capture_time = 0.0
        self.fps = 0.0
        self.frame_count = 0

    @property
    def page(self) -> Optional[Page]:
        return self._page

    def _find_chrome_executable(self) -> Optional[str]:
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return None

    def _ensure_canvas_ready(self, timeout: float = 60.0) -> bool:
        if self._page is None:
            return False

        is_parsec = "parsec" in self.guacamole_url.lower()

        if is_parsec:
            print(f"[ParsecCapture] Waiting for live game video stream (timeout {timeout}s)...", flush=True)
            t_start = time.time()
            prompted = False
            while time.time() - t_start < timeout:
                # In Parsec web client, the active game stream is rendered into a <video> element
                video_el = self._page.query_selector("video")
                if video_el:
                    print("[ParsecCapture] Live game video stream detected and active!", flush=True)
                    return True

                # Check if at login screen
                pwd_input = self._page.query_selector("input[type='password']")
                if pwd_input and not prompted:
                    print(
                        "[ParsecCapture] Parsec Login required! Please log in to Parsec in the opened browser window.",
                        flush=True,
                    )
                    prompted = True

                time.sleep(1.0)

            print(f"[ParsecCapture Warning] Video stream not detected within {timeout}s. Current URL: {self._page.url}", flush=True)
            return False

        else:
            # Guacamole display canvas
            selectors = "#display, .guac-display, canvas"
            stream_el = self._page.query_selector(selectors)
            if stream_el:
                print("[GuacamoleCapture] Remote canvas active.", flush=True)
                return True

            # Check for login inputs
            user_input = self._page.query_selector("input[type='text']")
            pwd_input = self._page.query_selector("input[type='password']")
            btn = self._page.query_selector("input[type='submit'], button[type='submit'], button")

            if pwd_input and self.username and self.password:
                print(f"[GuacamoleCapture] Attempting auto-login for user '{self.username}'...", flush=True)
                if user_input:
                    user_input.fill(self.username)
                pwd_input.fill(self.password)
                if btn:
                    btn.click()
                time.sleep(2.0)
            elif pwd_input:
                print(
                    "[GuacamoleCapture] Login screen detected. Please log into Guacamole in the opened browser window.",
                    flush=True,
                )

            # Poll for canvas up to timeout seconds
            print(f"[GuacamoleCapture] Waiting up to {timeout}s for connection canvas...", flush=True)
            t_start = time.time()
            while time.time() - t_start < timeout:
                stream_el = self._page.query_selector(selectors)
                if stream_el:
                    print("[GuacamoleCapture] Remote desktop canvas detected and verified active.", flush=True)
                    return True
                time.sleep(1.0)

            print(
                f"[GuacamoleCapture Warning] Canvas not detected within {timeout}s. Current URL: {self._page.url}",
                flush=True,
            )
            return False

    def connect(self) -> bool:
        """
        Connects to browser via CDP or launches a new visible browser instance with persistent profile.
        """
        if not HAS_PLAYWRIGHT:
            print("[WebCapture] Playwright not found in environment.", flush=True)
            return False

        self._playwright = sync_playwright().start()

        target_keyword = "parsec" if "parsec" in self.guacamole_url.lower() else "guacamole"

        # 1. Try CDP connection to existing browser session
        try:
            print(f"[WebCapture] Connecting to CDP at {self.cdp_endpoint}...", flush=True)
            self._browser = self._playwright.chromium.connect_over_cdp(self.cdp_endpoint, timeout=2500)
            self._context = self._browser.contexts[0]

            # Find existing remote tab (Parsec, MapleStory, or Guacamole)
            target_page = None
            for p in self._context.pages:
                url_l = p.url.lower()
                try:
                    title_l = (p.title() or "").lower()
                except Exception:
                    title_l = ""
                if any(k in url_l or k in title_l for k in ["parsec", "maple", "guacamole"]):
                    target_page = p
                    break

            if not target_page and len(self._context.pages) > 0:
                target_page = self._context.pages[0]

            if target_page:
                self._page = target_page
                print(f"[WebCapture] Attached directly to existing browser tab: {self._page.url}", flush=True)
                return True
            else:
                print("[WebCapture Warning] No matching open tab found in existing browser.", flush=True)
                return False

        except Exception as cdp_err:
            print(f"[WebCapture] CDP connection error: {cdp_err}", flush=True)
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

            if frame is not None:
                cur_shape = frame.shape[:2]
                if self._game_crop_bounds is None or getattr(self, "_last_raw_shape", None) != cur_shape:
                    self._last_raw_shape = cur_shape
                    sub = frame[::8, ::8]
                    mask = np.any(sub > 15, axis=2)
                    ys, xs = np.where(mask)
                    if len(xs) > 100 and len(ys) > 100:
                        y1, y2 = int(ys.min()) * 8, int(ys.max() + 1) * 8
                        x1, x2 = int(xs.min()) * 8, int(xs.max() + 1) * 8
                        if (x2 - x1) > 400 and (y2 - y1) > 300:
                            self._game_crop_bounds = (y1, y2, x1, x2)
                            print(f"[GuacamoleCapture] Auto-detected game canvas: {x2-x1}x{y2-y1} at ({x1},{y1})", flush=True)

                if self._game_crop_bounds is not None:
                    y1, y2, x1, x2 = self._game_crop_bounds
                    frame = frame[y1:y2, x1:x2]

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
