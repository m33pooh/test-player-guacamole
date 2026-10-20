import ctypes
import time
from abc import ABC, abstractmethod
from typing import Optional

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False


VK_KEYS = {
    "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34, "5": 0x35,
    "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39, "0": 0x30,
    "q": 0x51, "w": 0x57, "e": 0x45, "r": 0x52, "t": 0x54, "y": 0x59,
    "f": 0x46, "m": 0x4D, "escape": 0x1B, "enter": 0x0D, "space": 0x20,
}


class BaseKeyboardController(ABC):
    @abstractmethod
    def press(self, key: str, delay: float = 0.03):
        pass


class PlaywrightKeyboardController(BaseKeyboardController):
    def __init__(self, page):
        self.page = page

    def press(self, key: str, delay: float = 0.04):
        if self.page:
            try:
                delay_ms = int(max(25, delay * 1000))
                self.page.keyboard.press(key, delay=delay_ms)
                if delay > 0:
                    time.sleep(delay)
            except Exception:
                pass


class OSKeyboardController(BaseKeyboardController):
    def press(self, key: str, delay: float = 0.03):
        if HAS_PYAUTOGUI:
            try:
                pyautogui.press(key.lower())
                if delay > 0:
                    time.sleep(delay)
                return
            except Exception:
                pass

        # Windows ctypes fallback
        vk = VK_KEYS.get(key.lower())
        if vk and hasattr(ctypes, "windll"):
            try:
                ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                time.sleep(max(0.01, delay))
                ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
            except Exception:
                pass


class DryRunKeyboardController(BaseKeyboardController):
    def press(self, key: str, delay: float = 0.03):
        pass
