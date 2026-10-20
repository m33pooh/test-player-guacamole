import time
from typing import Optional, Tuple
import numpy as np

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from app.controller.keyboard import (
    BaseKeyboardController,
    DryRunKeyboardController,
    OSKeyboardController,
    PlaywrightKeyboardController,
)
from app.controller.mouse import (
    BaseMouseController,
    DryRunMouseController,
    OSMouseController,
    PlaywrightMouseController,
)
from config.settings import ControllerConfig


class ActionController:
    """
    Unified Action Controller for Keyboard, Mouse, and Screen Capture.
    Supports Playwright Browser CDP connection, Direct OS (PyAutoGUI/Win32), and Dry-Run.
    Preserves natural browser / game screen scaling without force-resizing.
    """
    def __init__(self, config: Optional[ControllerConfig] = None):
        self.config = config or ControllerConfig()
        self.keyboard: BaseKeyboardController = DryRunKeyboardController()
        self.mouse: BaseMouseController = DryRunMouseController()
        self.playwright = None
        self.browser = None
        self.page = None
        self.is_connected = False
        self.backend_type = "dry_run"

    def connect(self, mode: str = "auto") -> bool:
        target_mode = mode if mode != "auto" else self.config.backend

        # 1. Try Playwright CDP Connection
        if target_mode in ["auto", "playwright"] and HAS_PLAYWRIGHT:
            try:
                self.playwright = sync_playwright().start()
                try:
                    self.browser = self.playwright.chromium.connect_over_cdp(
                        self.config.cdp_url, timeout=3000
                    )
                except Exception:
                    self.browser = None

                if self.browser:
                    # Find Guacamole or game page across contexts
                    for ctx in self.browser.contexts:
                        for p in ctx.pages:
                            if "guacamole" in p.url or "game" in p.url:
                                self.page = p
                                break
                        if self.page:
                            break

                    if not self.page and self.browser.contexts:
                        pages = self.browser.contexts[0].pages
                        if pages:
                            self.page = pages[0]
                        else:
                            self.page = self.browser.contexts[0].new_page()
                            self.page.goto(self.config.guacamole_url)

                # If CDP not running but user explicitly requested Playwright, launch browser directly
                if not self.page and target_mode == "playwright":
                    print("[Controller] CDP on port 9222 not found. Launching Chromium window in natural mode...")
                    self.browser = self.playwright.chromium.launch(
                        headless=False,
                        args=[
                            "--start-maximized",
                            "--remote-debugging-port=9222",
                        ],
                    )
                    ctx = self.browser.new_context(no_viewport=True)
                    self.page = ctx.new_page()
                    self.page.goto(self.config.guacamole_url)

                if self.page:
                    self.page.bring_to_front()
                    try:
                        dpi = float(self.page.evaluate("() => window.devicePixelRatio || 1.0"))
                    except Exception:
                        dpi = 1.0
                    self.keyboard = PlaywrightKeyboardController(self.page)
                    self.mouse = PlaywrightMouseController(self.page, dpi_scale=dpi)
                    self.is_connected = True
                    self.backend_type = "playwright"
                    vp = self.page.viewport_size
                    vp_str = f"{vp['width']}x{vp['height']}" if vp else "natural/unrestricted"
                    print(f"[Controller] Playwright attached successfully to: {self.page.url} (DPI Scale: {dpi}x | Viewport: {vp_str})", flush=True)
                    return True
            except Exception as e:
                print(f"[Controller Warning] Playwright connection fallback: {e}", flush=True)

        # 2. OS Controller (PyAutoGUI / ctypes)
        if target_mode in ["auto", "os", "direct"]:
            self.keyboard = OSKeyboardController()
            self.mouse = OSMouseController()
            self.is_connected = True
            self.backend_type = "os"
            print("[Controller] Direct OS Controller active (PyAutoGUI / ctypes).", flush=True)
            return True

        # 3. Dry Run Fallback
        self.keyboard = DryRunKeyboardController()
        self.mouse = DryRunMouseController()
        self.is_connected = True
        self.backend_type = "dry_run"
        print("[Controller] Operating in Dry-Run mode.", flush=True)
        return True

    def capture_frame(self) -> Optional[np.ndarray]:
        """Captures page/screen as OpenCV BGR image at native resolution."""
        if self.page:
            try:
                raw_bytes = self.page.screenshot(type="jpeg", quality=75, timeout=2000)
                if HAS_OPENCV:
                    return cv2.imdecode(np.frombuffer(raw_bytes, np.uint8), cv2.IMREAD_COLOR)
            except Exception:
                pass
        return None

    def click(self, x: int, y: int, button: str = "left"):
        self.mouse.click(x, y, button=button)

    def dblclick(self, x: int, y: int):
        self.mouse.dblclick(x, y)

    def move(self, x: int, y: int):
        self.mouse.move(x, y)

    def press(self, key: str, delay: float = 0.03):
        self.keyboard.press(key, delay=delay)

    def drag_relative(self, dx: int, dy: int, button: str = "right"):
        self.mouse.drag_relative(dx, dy, button=button)

    def close(self):
        """
        Detaches from the controller cleanly.
        Keeps the browser open so the user's game session is never closed.
        """
        self.page = None
        self.browser = None
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass
        self.playwright = None
        self.is_connected = False
