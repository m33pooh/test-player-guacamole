import os
import sys
import time
from typing import Optional, List, Tuple
import numpy as np
import cv2

try:
    import ctypes
    from ctypes import wintypes
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

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


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ('biSize', wintypes.DWORD),
        ('biWidth', wintypes.LONG),
        ('biHeight', wintypes.LONG),
        ('biPlanes', wintypes.WORD),
        ('biBitCount', wintypes.WORD),
        ('biCompression', wintypes.DWORD),
        ('biSizeImage', wintypes.DWORD),
        ('biXPelsPerMeter', wintypes.LONG),
        ('biYPelsPerMeter', wintypes.LONG),
        ('biClrUsed', wintypes.DWORD),
        ('biClrImportant', wintypes.DWORD),
    ]


class DXGICapture:
    """
    High-performance Windows Capture Engine.
    Supports:
    1. Direct Window Capture (PrintWindow on default desktop, captures existing Chrome/Parsec/Maple windows directly)
    2. DXGI Desktop Duplication (dxcam)
    3. MSS Screen Capture Fallback
    """

    def __init__(self, target_fps: int = 60, window_keywords: Optional[List[str]] = None):
        self.target_fps = target_fps
        self.window_keywords = window_keywords or ["parsec", "maplestory", "maple", "chrome", "edge"]
        self.camera = None
        self.sct = None
        self.target_hwnd = None
        self.target_title = ""
        self.is_connected = False
        self.fps = 0.0
        self.last_time = 0.0

        if HAS_WIN32:
            self.user32 = ctypes.windll.user32
            self.gdi32 = ctypes.windll.gdi32
            try:
                # Ensure thread has access to default interactive desktop
                h_desk = self.user32.OpenDesktopW("default", 0, False, 0x01FF)
                if h_desk:
                    self.user32.SetThreadDesktop(h_desk)
            except Exception:
                pass

    def find_target_window(self) -> Optional[int]:
        if not HAS_WIN32:
            return None

        candidates = []

        def enum_cb(hwnd, extra):
            if self.user32.IsWindowVisible(hwnd):
                length = self.user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    self.user32.GetWindowTextW(hwnd, buff, length + 1)
                    candidates.append((hwnd, buff.value))
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        self.user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

        # Match in keyword priority order: e.g. 'parsec' first, then 'maplestory', etc.
        for kw in self.window_keywords:
            kw_l = kw.lower()
            for hwnd, title in candidates:
                if kw_l in title.lower():
                    self.target_hwnd = hwnd
                    self.target_title = title
                    return hwnd

        return None

    def connect(self) -> bool:
        # 1. Try Direct Window Capture first (captures existing Parsec/Maple browser window)
        hwnd = self.find_target_window()
        if hwnd:
            self.is_connected = True
            safe_title = self.target_title.encode('ascii', errors='replace').decode('ascii')
            print(f"[WindowCapture] Found and attached directly to window: '{safe_title}' (HWND: {self.target_hwnd})", flush=True)
            return True

        # 2. Try DXGI dxcam
        if HAS_DXCAM:
            try:
                self.camera = dxcam.create(output_color="BGR")
                self.camera.start(target_fps=self.target_fps)
                self.is_connected = True
                print("[DXGICapture] Initialized DXGI Desktop Duplication (dxcam).", flush=True)
                return True
            except Exception as e:
                print(f"[DXGICapture Warning] dxcam initialization failed: {e}", flush=True)

        # 3. Try MSS fallback
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

        # 1. Window Capture via PrintWindow
        if self.target_hwnd and HAS_WIN32:
            try:
                rect = wintypes.RECT()
                self.user32.GetWindowRect(self.target_hwnd, ctypes.byref(rect))
                w = rect.right - rect.left
                h = rect.bottom - rect.top

                if w > 100 and h > 100:
                    hwndDC = self.user32.GetWindowDC(self.target_hwnd)
                    mfcDC = self.gdi32.CreateCompatibleDC(hwndDC)
                    saveBitMap = self.gdi32.CreateCompatibleBitmap(hwndDC, w, h)
                    self.gdi32.SelectObject(mfcDC, saveBitMap)

                    # PW_RENDERFULLCONTENT = 2
                    self.user32.PrintWindow(self.target_hwnd, mfcDC, 2)

                    bmi = BITMAPINFOHEADER()
                    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                    bmi.biWidth = w
                    bmi.biHeight = -h
                    bmi.biPlanes = 1
                    bmi.biBitCount = 32
                    bmi.biCompression = 0

                    buf = ctypes.create_string_buffer(w * h * 4)
                    self.gdi32.GetDIBits(mfcDC, saveBitMap, 0, h, buf, ctypes.byref(bmi), 0)

                    self.gdi32.DeleteObject(saveBitMap)
                    self.gdi32.DeleteDC(mfcDC)
                    self.user32.ReleaseDC(self.target_hwnd, hwndDC)

                    raw = np.frombuffer(buf, dtype=np.uint8).reshape((h, w, 4))
                    frame = raw[:, :, :3]
            except Exception:
                frame = None

        # 2. DXCAM fallback
        if frame is None and self.camera is not None:
            frame = self.camera.get_latest_frame()

        # 3. MSS fallback
        if frame is None and self.sct is not None:
            try:
                monitor = self.sct.monitors[1]
                raw = self.sct.grab(monitor)
                frame = np.array(raw)[:, :, :3]
            except Exception:
                frame = None

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
