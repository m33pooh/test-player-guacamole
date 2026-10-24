import time
from typing import Dict, Any, Optional
from maple.app.controller.input_driver import GuacamoleInputDriver


class ChannelSurfer:
    """
    Anti-KS & Channel Surfing Engine.
    Monitors presence of other players (Red dots) on the minimap.
    If another player lingers for more than threshold (default 10s),
    initiates an automated channel hop to avoid conflict and detection.
    """

    def __init__(
        self,
        driver: GuacamoleInputDriver,
        ks_threshold_sec: float = 10.0,
        change_channel_hotkey: Optional[str] = None,
    ):
        self.driver = driver
        self.ks_threshold_sec = ks_threshold_sec
        self.change_channel_hotkey = change_channel_hotkey

        self.other_player_first_seen = 0.0
        self.is_changing_channel = False
        self.current_channel = 1

    def update_other_players(self, other_players_count: int) -> bool:
        """
        Updates tracking timer.
        Returns True if a channel change should be triggered.
        """
        if self.ks_threshold_sec <= 0:
            return False

        now = time.time()
        if other_players_count > 0:
            if self.other_player_first_seen == 0.0:
                self.other_player_first_seen = now
                print(f"[Anti-KS] Other player detected! Starting linger timer...", flush=True)
            elif (now - self.other_player_first_seen) >= self.ks_threshold_sec:
                print(f"[Anti-KS] Other player present for > {self.ks_threshold_sec}s! Triggering Channel Change...", flush=True)
                return True
        else:
            self.other_player_first_seen = 0.0

        return False

    def execute_channel_change(self) -> bool:
        """
        Executes MapleStory Change Channel keyboard sequence:
        1. If hotkey defined, press hotkey
        2. Otherwise: Esc -> Enter (opens CC dialog) -> ArrowRight (next channel) -> Enter (confirm)
        """
        print("[ChannelSurfer] Executing Change Channel sequence...", flush=True)
        self.is_changing_channel = True

        if self.change_channel_hotkey:
            self.driver.press_key(self.change_channel_hotkey)
            time.sleep(0.3)
            self.driver.press_key("Enter")
        else:
            # Standard sequence
            self.driver.press_key("Escape")
            time.sleep(0.3)
            self.driver.press_key("Enter")
            time.sleep(0.4)
            self.driver.press_key("ArrowRight")
            time.sleep(0.2)
            self.driver.press_key("Enter")

        # Loading wait time
        time.sleep(3.5)

        self.current_channel = (self.current_channel % 30) + 1
        self.other_player_first_seen = 0.0
        self.is_changing_channel = False
        print(f"[ChannelSurfer] Successfully hopped to channel {self.current_channel}!", flush=True)
        return True
