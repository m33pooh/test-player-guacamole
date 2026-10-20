import time
from typing import Optional
import numpy as np
import cv2

try:
    import dxcam
    HAS_DXCAM = True
except ImportError:
    HAS_DXCAM = False

try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False


class DXGICapture:
    """
    DirectX / Screen capture fallback for local MapleStory windows.
    Uses dxcam (DXGI Desktop Duplication 60+ FPS) or mss as fallback.
    """

    def __init__(self, target_fps: int = 60):
        self.target_fps = target_fps
        self.camera = None
        self.sct = None
        self.is_connected = False
        self.fps = 0.0
        self.last_time = 0.0

    def connect(self) -> bool:
        if HAS_DXCAM:
            try:
                self.camera = dxcam.create(output_color="BGR")
                self.camera.start(target_fps=self.target_fps)
                self.is_connected = True
                print("[DXGICapture] Initialized DXGI Desktop Duplication (dxcam).", flush=True)
                return True
            except Exception as e:
                print(f"[DXGICapture Warning] dxcam initialization failed: {e}", flush=True)

        if HAS_MSS:
            try:
                self.sct = mss.mss()
                self.is_connected = True
                print("[DXGICapture] Initialized mss screen capture fallback.", flush=True)
                return True
            except Exception as e:
                print(f"[DXGICapture Error] mss initialization failed: {e}", flush=True)

        return False

    def capture_frame(self) -> Optional[np.ndarray]:
        if not self.is_connected:
            return None

        frame = None
        if self.camera is not None:
            frame = self.camera.get_latest_frame()
        elif self.sct is not None:
            monitor = self.sct.monitors[1]
            raw = self.sct.grab(monitor)
            frame = np.array(raw)[:, :, :3]

        if frame is not None:
            now = time.time()
            dt = now - self.last_time
            if dt > 0:
                self.fps = 0.9 * self.fps + 0.1 * (1.0 / dt) if self.fps > 0 else (1.0 / dt)
            self.last_time = now

        return frame

    def close(self):
        if self.camera is not None:
            try:
                self.camera.stop()
            except Exception:
                pass
        if self.sct is not None:
            try:
                self.sct.close()
            except Exception:
                pass
