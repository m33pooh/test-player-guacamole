import time
from typing import List, Optional

from maple.app.controller.timing_jitter import GaussianTimingJitter


class GuacamoleInputDriver:
    """
    Input driver designed for Guacamole Web Remote and direct browser contexts.
    Dispatches keyboard events and mouse interactions to the remote MapleStory desktop.
    """

    def __init__(self, page=None, jitter: Optional[GaussianTimingJitter] = None):
        self.page = page
        self.jitter = jitter or GaussianTimingJitter()
        self.canvas_focused = False

    def set_page(self, page):
        self.page = page
        self.canvas_focused = False

    def focus_game_canvas(self):
        """
        Ensures the remote Guacamole canvas has focus to receive keyboard events.
        """
        if self.page is None:
            return

        try:
            # Common Guacamole display selectors
            canvas = self.page.query_selector("canvas, #display, .guac-display")
            if canvas:
                canvas.click()
            else:
                self.page.mouse.click(640, 360)
            self.canvas_focused = True
        except Exception as e:
            print(f"[InputDriver Warning] Failed to focus canvas: {e}", flush=True)

    def press_key(self, key: str, duration: Optional[float] = None):
        """
        Presses and releases a single key with humanized Gaussian delay.
        """
        if not self.canvas_focused and self.page is not None:
            self.focus_game_canvas()

        hold_time = duration or self.jitter.get_press_duration()

        if self.page is not None:
            try:
                self.page.keyboard.down(key)
                time.sleep(hold_time)
                self.page.keyboard.up(key)
            except Exception as e:
                print(f"[InputDriver Error] Failed to press {key}: {e}", flush=True)
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
        if not self.canvas_focused and self.page is not None:
            self.focus_game_canvas()

        duration = hold_time or self.jitter.get_press_duration(mean=0.090, std=0.015)

        if self.page is not None:
            try:
                for k in keys:
                    self.page.keyboard.down(k)
                time.sleep(duration)
                for k in reversed(keys):
                    self.page.keyboard.up(k)
            except Exception as e:
                print(f"[InputDriver Error] Failed combo {keys}: {e}", flush=True)
        else:
            print(f"[InputDriver Sim] Combo {keys} ({duration*1000:.1f}ms)", flush=True)
            time.sleep(duration)

    def walk(self, direction: str, duration: float):
        """
        Walks horizontally in a direction ("left" or "right").
        """
        key = "ArrowLeft" if direction.lower() == "left" else "ArrowRight"
        if not self.canvas_focused and self.page is not None:
            self.focus_game_canvas()

        if self.page is not None:
            try:
                self.page.keyboard.down(key)
                time.sleep(max(0.05, duration))
                self.page.keyboard.up(key)
            except Exception as e:
                print(f"[InputDriver Error] Walk error: {e}", flush=True)
        else:
            print(f"[InputDriver Sim] Walk {direction} for {duration:.2f}s", flush=True)
            time.sleep(duration)

    def flash_jump(self, direction: str, jump_key: str = "Alt", attack_key: Optional[str] = None):
        """
        Executes a 2D MapleStory Flash Jump:
        Direction + Jump -> Jump again -> Optional Attack/Mobbing skill.
        """
        dir_key = "ArrowLeft" if direction.lower() == "left" else "ArrowRight"
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
        Clicks a coordinate on the Guacamole canvas.
        """
        if self.page is not None:
            try:
                self.page.mouse.click(x, y, button=button)
            except Exception as e:
                print(f"[InputDriver Error] Click error: {e}", flush=True)
        else:
            print(f"[InputDriver Sim] Click ({x}, {y}) [{button}]", flush=True)
