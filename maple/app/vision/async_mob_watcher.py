import threading
import time
from typing import Dict, Any, Optional, Tuple
import cv2
import numpy as np

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from maple.app.vision.mob_detector import MobDetector


class AsyncMobWatcher(threading.Thread):
    """
    Dedicated background worker thread for 24/7 continuous monster counting on the platform.
    Runs asynchronously and independently of main thread actions, sleep delays, and inputs.
    
    Provides:
    - `get_latest_scan()`: Instantaneous (0ms) thread-safe read of mob presence, counts, and positions.
    - `get_latest_frame()`: Instantaneous read of latest captured frame (zero roundtrip delay).
    """

    def __init__(
        self,
        cdp_endpoint: str = "http://localhost:9222",
        player_center: Tuple[int, int] = (1065, 700),
        reach_left: int = 600,
        reach_right: int = 375,
        target_fps: float = 20.0,
        mob_detector: Optional[MobDetector] = None,
    ):
        super().__init__(name="AsyncMobWatcherThread", daemon=True)
        self.cdp_endpoint = cdp_endpoint
        self.player_center = player_center
        self.reach_left = reach_left
        self.reach_right = reach_right
        self.target_fps = target_fps
        self.mob_detector = mob_detector or MobDetector()

        self.stop_event = threading.Event()
        self.ready_event = threading.Event()
        self._lock = threading.Lock()

        self._latest_scan: Dict[str, Any] = {
            "left": {"active": False, "bars": [], "tags": [], "count": 0},
            "right": {"active": False, "bars": [], "tags": [], "count": 0},
            "any_mobs": False,
            "total_count": 0,
        }
        self._latest_frame: Optional[np.ndarray] = None
        self._last_scan_time: float = 0.0
        self.scan_count: int = 0
        self.fps: float = 0.0
        self._game_crop_bounds: Optional[Tuple[int, int, int, int]] = None

    def get_latest_scan(self) -> Dict[str, Any]:
        """Instantaneous (0ms) thread-safe access to latest mob count & locations."""
        with self._lock:
            return self._latest_scan.copy()

    def clear_scan(self):
        """Immediately clears mob cache after monster kill to prevent ghost shots."""
        with self._lock:
            self._latest_scan = {
                "left": {"active": False, "bars": [], "tags": [], "count": 0},
                "right": {"active": False, "bars": [], "tags": [], "count": 0},
                "any_mobs": False,
                "total_count": 0,
            }

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Instantaneous (0ms) thread-safe access to latest captured frame."""
        with self._lock:
            if self._latest_frame is not None:
                return self._latest_frame.copy()
            return None

    def stop(self, timeout: float = 2.0):
        """Signals background thread to terminate cleanly."""
        self.stop_event.set()
        if self.is_alive():
            self.join(timeout=timeout)

    def run(self):
        if not HAS_PLAYWRIGHT:
            print("[AsyncMobWatcher] Playwright not found; continuous watcher disabled.", flush=True)
            self.ready_event.set()
            return

        print(f"[AsyncMobWatcher] Starting dedicated background CDP thread ({self.cdp_endpoint})...", flush=True)
        playwright_instance = sync_playwright().start()

        try:
            browser = playwright_instance.chromium.connect_over_cdp(self.cdp_endpoint, timeout=3000)
            page = browser.contexts[0].pages[0]
            print(f"[AsyncMobWatcher] Connected! Continuous 24/7 mob scanner active on: {page.url}", flush=True)
            self.ready_event.set()

            last_t = time.time()
            frame_interval = 1.0 / max(5.0, min(30.0, self.target_fps))

            while not self.stop_event.is_set():
                cycle_start = time.time()
                try:
                    bytes_data = page.screenshot(type="jpeg", quality=75, timeout=1200)
                    nparr = np.frombuffer(bytes_data, np.uint8)
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                    if frame is None:
                        time.sleep(0.04)
                        continue

                    # Auto-detect game canvas viewport on startup or whenever browser/window resizes
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

                    if self._game_crop_bounds is not None:
                        y1, y2, x1, x2 = self._game_crop_bounds
                        frame = frame[y1:y2, x1:x2]

                    # High-speed compact island scan
                    scan_res = self.mob_detector.scan_platform_mobs(
                        frame,
                        player_center=self.player_center,
                        reach_left=self.reach_left,
                        reach_right=self.reach_right,
                    )

                    now = time.time()
                    dt = now - last_t
                    last_t = now
                    instant_fps = (1.0 / dt) if dt > 0 else 0.0

                    with self._lock:
                        self._latest_scan = scan_res
                        self._latest_frame = frame
                        self._last_scan_time = now
                        self.scan_count += 1
                        self.fps = 0.9 * self.fps + 0.1 * instant_fps

                    sleep_dur = frame_interval - (time.time() - cycle_start)
                    if sleep_dur > 0:
                        time.sleep(sleep_dur)
                    else:
                        time.sleep(0.01)

                except Exception as ex:
                    # Ignore occasional browser transient errors and retry
                    time.sleep(0.08)

        except Exception as conn_err:
            print(f"[AsyncMobWatcher Error] Failed to connect: {conn_err}", flush=True)
            self.ready_event.set()
        finally:
            try:
                playwright_instance.stop()
            except Exception:
                pass
            print("[AsyncMobWatcher] Background thread stopped.", flush=True)
