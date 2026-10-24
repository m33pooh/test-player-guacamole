import time
from typing import List, Optional

from maple.app.controller.timing_jitter import GaussianTimingJitter

try:
    import ctypes
    HAS_WIN32 = True
    user32 = ctypes.windll.user32
except ImportError:
    HAS_WIN32 = False

VK_MAP = {
    "left": 0x25, "right": 0x27, "up": 0x26, "down": 0x28,
    "arrowleft": 0x25, "arrowright": 0x27, "arrowup": 0x26, "arrowdown": 0x28,
    "space": 0x20, "alt": 0x12, "ctrl": 0x11, "control": 0x11, "shift": 0x10,
    "enter": 0x0D, "esc": 0x1B, "pagedown": 0x22, "pageup": 0x21,
    "delete": 0x2E, "insert": 0x2D, "home": 0x24, "end": 0x23,
}


def get_vk_code(key: str) -> int:
    k = key.lower()
    if k in VK_MAP:
        return VK_MAP[k]
    if len(key) == 1:
        c = ord(key.upper())
        if (65 <= c <= 90) or (48 <= c <= 57):
            return c
    return 0


PLAYWRIGHT_KEY_MAP = {
    "left": "ArrowLeft", "arrowleft": "ArrowLeft",
    "right": "ArrowRight", "arrowright": "ArrowRight",
    "up": "ArrowUp", "arrowup": "ArrowUp",
    "down": "ArrowDown", "arrowdown": "ArrowDown",
    "ctrl": "Control", "control": "Control",
    "alt": "Alt", "shift": "Shift",
    "esc": "Escape", "escape": "Escape",
    "enter": "Enter", "space": "Space",
    "pagedown": "PageDown", "pageup": "PageUp",
    "home": "Home", "end": "End",
    "delete": "Delete", "insert": "Insert",
}


def normalize_playwright_key(key: str) -> str:
    k = key.lower()
    return PLAYWRIGHT_KEY_MAP.get(k, key)


class GuacamoleInputDriver:
    """
    Input driver designed for Guacamole Web Remote and direct window contexts.
    Dispatches keyboard events and mouse interactions to the remote MapleStory desktop.
    """

    def __init__(self, page=None, hwnd: Optional[int] = None, jitter: Optional[GaussianTimingJitter] = None):
        self.page = page
        self.hwnd = hwnd
        self.jitter = jitter or GaussianTimingJitter()
        self.canvas_focused = False

    def set_page(self, page):
        self.page = page
        self.canvas_focused = False

    def set_hwnd(self, hwnd: int):
        self.hwnd = hwnd
        self.canvas_focused = False

    def focus_game_canvas(self):
        """
        Ensures the game window/canvas has focus to receive keyboard events without resizing.
        """
        if self.page is not None:
            try:
                canvas = self.page.query_selector("canvas, video, #display, .guac-display, [id*='parsec'], [class*='parsec']")
                if canvas:
                    canvas.click()
                self.canvas_focused = True
            except Exception as e:
                print(f"[InputDriver Warning] Failed to focus canvas: {e}", flush=True)
        elif self.hwnd and HAS_WIN32:
            try:
                user32.SetForegroundWindow(self.hwnd)
                self.canvas_focused = True
            except Exception:
                pass

    def press_key(self, key: str, duration: Optional[float] = None):
        """
        Presses and releases a single key with humanized Gaussian delay.
        """
        if not self.canvas_focused:
            self.focus_game_canvas()

        hold_time = duration or self.jitter.get_press_duration()

        if self.page is not None:
            pk = normalize_playwright_key(key)
            try:
                self.page.keyboard.down(pk)
                time.sleep(hold_time)
                self.page.keyboard.up(pk)
            except Exception as e:
                print(f"[InputDriver Error] Failed to press {pk}: {e}", flush=True)
        elif HAS_WIN32:
            vk = get_vk_code(key)
            if vk > 0:
                user32.keybd_event(vk, 0, 0, 0)
                time.sleep(hold_time)
                user32.keybd_event(vk, 0, 2, 0)
            else:
                print(f"[InputDriver Sim] Press {key} ({hold_time*1000:.1f}ms)", flush=True)
                time.sleep(hold_time)
        else:
            print(f"[InputDriver Sim] Press {key} ({hold_time*1000:.1f}ms)", flush=True)
            time.sleep(hold_time)

    def tap_key(self, key: str):
        """
        Quick tap of a key.
        """
        duration = self.jitter.get_press_duration(mean=0.045, std=0.008, bounds=(0.02, 0.08))
        self.press_key(key, duration=duration)

    def press_sequence(self, keys: List[str], inter_delay: Optional[float] = None):
        """
        Presses a sequence of keys with natural delays in between.
        Useful for solving Rune arrow combinations or skill chains.
        """
        for i, key in enumerate(keys):
            self.press_key(key)
            if i < len(keys) - 1:
                delay = inter_delay or self.jitter.get_interval_delay()
                time.sleep(delay)

    def press_combo(self, keys: List[str], hold_time: Optional[float] = None):
        """
        Presses multiple keys simultaneously, e.g. Down + Jump.
        """
        if not self.canvas_focused:
            self.focus_game_canvas()

        duration = hold_time or self.jitter.get_press_duration(mean=0.090, std=0.015)

        if self.page is not None:
            try:
                for k in keys:
                    pk = normalize_playwright_key(k)
                    self.page.keyboard.down(pk)
                time.sleep(duration)
                for k in reversed(keys):
                    pk = normalize_playwright_key(k)
                    self.page.keyboard.up(pk)
            except Exception as e:
                print(f"[InputDriver Error] Failed combo {keys}: {e}", flush=True)
        elif HAS_WIN32:
            vks = [get_vk_code(k) for k in keys if get_vk_code(k) > 0]
            for vk in vks:
                user32.keybd_event(vk, 0, 0, 0)
            time.sleep(duration)
            for vk in reversed(vks):
                user32.keybd_event(vk, 0, 2, 0)
        else:
            print(f"[InputDriver Sim] Combo {keys} ({duration*1000:.1f}ms)", flush=True)
            time.sleep(duration)

    def walk(self, direction: str, duration: float):
        """
        Walks horizontally in a direction ("left" or "right") by holding the key for duration.
        """
        key = "ArrowLeft" if direction.lower() == "left" else "ArrowRight"
        if not self.canvas_focused:
            self.focus_game_canvas()

        hold_time = max(0.05, duration)
        if self.page is not None:
            try:
                self.page.keyboard.down(key)
                time.sleep(hold_time)
                self.page.keyboard.up(key)
            except Exception as e:
                print(f"[InputDriver Error] Walk error: {e}", flush=True)
                try:
                    self.page.keyboard.up(key)
                except Exception:
                    pass
        elif HAS_WIN32:
            vk = get_vk_code(key)
            user32.keybd_event(vk, 0, 0, 0)
            time.sleep(hold_time)
            user32.keybd_event(vk, 0, 2, 0)
        else:
            print(f"[InputDriver Sim] Walk {direction} for {duration:.2f}s", flush=True)
            time.sleep(hold_time)

    def walk_and_loot(self, direction: str, duration: float, loot_key: str = "z"):
        """
        Smoothly holds down the direction key for the calculated duration
        while continuously tapping the loot key (Z) along the path.
        """
        key = "ArrowLeft" if direction.lower() == "left" else "ArrowRight"
        if not self.canvas_focused:
            self.focus_game_canvas()

        hold_time = max(0.10, duration)
        start_t = time.time()

        if self.page is not None:
            try:
                self.page.keyboard.down(key)
                while (time.time() - start_t) < hold_time:
                    self.tap_key(loot_key)
                    time.sleep(0.08)
                self.page.keyboard.up(key)
            except Exception as e:
                print(f"[InputDriver Error] Walk and loot error: {e}", flush=True)
                try:
                    self.page.keyboard.up(key)
                except Exception:
                    pass
        elif HAS_WIN32:
            vk = get_vk_code(key)
            user32.keybd_event(vk, 0, 0, 0)
            while (time.time() - start_t) < hold_time:
                self.tap_key(loot_key)
                time.sleep(0.08)
            user32.keybd_event(vk, 0, 2, 0)
        else:
            print(f"[InputDriver Sim] Walk and loot {direction} for {duration:.2f}s", flush=True)
            time.sleep(hold_time)

    def flash_jump(self, direction: str, jump_key: str = "Alt", attack_key: Optional[str] = None):
        """
        Executes a 2D MapleStory Flash Jump:
        Direction + Jump -> Jump again -> Optional Attack/Mobbing skill.
        """
        dir_key = "ArrowLeft" if direction.lower() == "left" else "ArrowRight"
        if not self.canvas_focused:
            self.focus_game_canvas()

        if self.page is not None:
            try:
                self.page.keyboard.down(dir_key)
                time.sleep(0.04)
                self.press_key(jump_key, duration=0.04)
                self.jitter.sleep_jitter(0.06, 0.01)
                self.press_key(jump_key, duration=0.04)
                if attack_key:
                    self.jitter.sleep_jitter(0.08, 0.01)
                    self.press_key(attack_key, duration=0.05)
                self.jitter.sleep_jitter(0.08, 0.02)
                self.page.keyboard.up(dir_key)
            except Exception as e:
                print(f"[InputDriver Error] Flash Jump error: {e}", flush=True)
        elif HAS_WIN32:
            vk_dir = get_vk_code(dir_key)
            user32.keybd_event(vk_dir, 0, 0, 0)
            time.sleep(0.04)
            self.press_key(jump_key, duration=0.04)
            self.jitter.sleep_jitter(0.06, 0.01)
            self.press_key(jump_key, duration=0.04)
            if attack_key:
                self.jitter.sleep_jitter(0.08, 0.01)
                self.press_key(attack_key, duration=0.05)
            self.jitter.sleep_jitter(0.08, 0.02)
            user32.keybd_event(vk_dir, 0, 2, 0)
        else:
            print(f"[InputDriver Sim] Flash Jump {direction} (jump={jump_key}, atk={attack_key})", flush=True)

    def down_jump(self, jump_key: str = "Alt"):
        """
        Drops down to the lower platform: Down + Jump.
        """
        self.press_combo(["ArrowDown", jump_key], hold_time=0.10)

    def rope_lift(self, rope_key: str = "v"):
        """
        Uses 5th job Rope Lift skill to ascend vertically.
        """
        self.press_key(rope_key, duration=0.08)

    def click(self, x: int, y: int, button: str = "left"):
        """
        Clicks a coordinate on the canvas / window.
        """
        if self.page is not None:
            try:
                self.page.mouse.click(x, y, button=button)
            except Exception as e:
                print(f"[InputDriver Error] Click error: {e}", flush=True)
        else:
            print(f"[InputDriver Sim] Click ({x}, {y}) [{button}]", flush=True)
