import ctypes
import time
from abc import ABC, abstractmethod
from typing import Optional, Tuple

try:
    import pyautogui
    HAS_PYAUTOGUI = True
    pyautogui.PAUSE = 0.05
    pyautogui.FAILSAFE = True
except ImportError:
    HAS_PYAUTOGUI = False


class BaseMouseController(ABC):
    @abstractmethod
    def move(self, x: int, y: int):
        pass

    @abstractmethod
    def click(self, x: int, y: int, button: str = "left"):
        pass

    @abstractmethod
    def dblclick(self, x: int, y: int):
        pass

    @abstractmethod
    def drag_relative(self, dx: int, dy: int, button: str = "right"):
        pass


class PlaywrightMouseController(BaseMouseController):
    def __init__(self, page, dpi_scale: float = 1.0):
        self.page = page
        self.dpi_scale = max(0.1, float(dpi_scale))
        self.last_pos = (853, 466)

    def _to_css(self, x: int, y: int) -> Tuple[int, int]:
        """Converts physical frame pixel coordinates to Playwright logical CSS coordinates."""
        return int(round(x / self.dpi_scale)), int(round(y / self.dpi_scale))

    def move(self, x: int, y: int):
        if self.page:
            try:
                cx, cy = self._to_css(x, y)
                self.page.mouse.move(cx, cy)
                self.last_pos = (x, y)
            except Exception:
                pass

    def click(self, x: int, y: int, button: str = "left"):
        if self.page:
            try:
                cx, cy = self._to_css(x, y)
                self.page.mouse.click(cx, cy, button=button)
                self.last_pos = (x, y)
            except Exception:
                pass

    def dblclick(self, x: int, y: int):
        if self.page:
            try:
                cx, cy = self._to_css(x, y)
                self.page.mouse.dblclick(cx, cy)
                self.last_pos = (x, y)
            except Exception:
                pass

    def drag_relative(self, dx: int, dy: int, button: str = "right"):
        if self.page:
            try:
                cur_x, cur_y = self.last_pos
                c_start_x, c_start_y = self._to_css(cur_x, cur_y)
                c_end_x, c_end_y = self._to_css(cur_x + dx, cur_y + dy)
                self.page.mouse.move(c_start_x, c_start_y)
                self.page.mouse.down(button=button)
                time.sleep(0.05)
                self.page.mouse.move(c_end_x, c_end_y, steps=5)
                time.sleep(0.05)
                self.page.mouse.up(button=button)
                self.last_pos = (cur_x + dx, cur_y + dy)
            except Exception:
                pass


class OSMouseController(BaseMouseController):
    def __init__(self):
        self.last_pos = (853, 466)

    def move(self, x: int, y: int):
        if HAS_PYAUTOGUI:
            try:
                pyautogui.moveTo(x, y)
                self.last_pos = (x, y)
                return
            except Exception:
                pass
        if hasattr(ctypes, "windll"):
            try:
                ctypes.windll.user32.SetCursorPos(x, y)
                self.last_pos = (x, y)
            except Exception:
                pass

    def click(self, x: int, y: int, button: str = "left"):
        if HAS_PYAUTOGUI:
            try:
                pyautogui.click(x, y, button=button)
                self.last_pos = (x, y)
                return
            except Exception:
                pass
        if hasattr(ctypes, "windll"):
            try:
                ctypes.windll.user32.SetCursorPos(x, y)
                btn_down = 2 if button == "left" else 8
                btn_up = 4 if button == "left" else 16
                ctypes.windll.user32.mouse_event(btn_down, 0, 0, 0, 0)
                time.sleep(0.03)
                ctypes.windll.user32.mouse_event(btn_up, 0, 0, 0, 0)
                self.last_pos = (x, y)
            except Exception:
                pass

    def dblclick(self, x: int, y: int):
        self.click(x, y)
        time.sleep(0.05)
        self.click(x, y)

    def drag_relative(self, dx: int, dy: int, button: str = "right"):
        cx, cy = self.last_pos
        if HAS_PYAUTOGUI:
            try:
                pyautogui.mouseDown(button=button)
                time.sleep(0.05)
                pyautogui.moveTo(cx + dx, cy + dy)
                time.sleep(0.05)
                pyautogui.mouseUp(button=button)
                self.last_pos = (cx + dx, cy + dy)
                return
            except Exception:
                pass


class DryRunMouseController(BaseMouseController):
    def move(self, x: int, y: int):
        pass

    def click(self, x: int, y: int, button: str = "left"):
        pass

    def dblclick(self, x: int, y: int):
        pass

    def drag_relative(self, dx: int, dy: int, button: str = "right"):
        pass
