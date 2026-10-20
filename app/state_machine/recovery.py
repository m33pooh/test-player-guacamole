import time
from typing import List, Optional, Tuple

from app.controller.controller import ActionController
from config.settings import GameCoordsConfig


class RecoveryStateHandler:
    """
    Death Respawn and Geometry Unstuck Handler.
    Handles:
    1. Clicking exact 'Respawn In Town' cyan modal button.
    2. Confirming town respawn transition.
    3. Unstuck maneuvers (dodge jump, camera swing, random WASD step).
    """
    def __init__(self, controller: ActionController, coords: Optional[GameCoordsConfig] = None):
        self.controller = controller
        self.coords = coords or GameCoordsConfig()

    def handle_death_respawn(self, revive_coords: Optional[Tuple[int, int]] = None, frame_shape: Optional[Tuple[int, int]] = None):
        """
        Executes sequence to respawn back in town after player death.
        Uses exact calibrated button position (X: 50% | Y: 72.8%) from live game frames.
        """
        print("[Death Recovery] Player DEAD. Clicking 'Respawn In Town' button...", flush=True)

        if frame_shape:
            h, w = frame_shape[:2]
        else:
            w, h = 1862, 1080

        # Exact calibrated 'Respawn in Town' cyan button is at X: 50%, Y: 72.8% (e.g. 930, 786 on 1080p)
        btn_y = int(h * 0.728)
        center_x = int(w * 0.50)

        if revive_coords and (int(h * 0.65) <= revive_coords[1] <= int(h * 0.82)):
            target_x, target_y = revive_coords
        else:
            target_x, target_y = center_x, btn_y

        print(f"[Death Recovery] Clicking Respawn In Town button at ({target_x}, {target_y})...", flush=True)
        self.controller.click(target_x, target_y)
        time.sleep(0.12)
        self.controller.dblclick(target_x, target_y)
        time.sleep(0.15)
        self.controller.click(target_x, target_y)
        time.sleep(0.15)

        # Send keyboard confirmation hotkeys
        self.controller.press("enter", delay=0.15)
        self.controller.press("space", delay=0.15)

        print("[Death Recovery] Respawn sequence complete. Waiting 4s for Town load...", flush=True)
        time.sleep(4.0)

    def handle_unstuck(self):
        """
        Executes anti-stuck maneuvers if the character is blocked by terrain or obstacles.
        """
        self.controller.press("escape", delay=0.1)
        self.controller.press("4", delay=0.2)
        self.controller.press("s", delay=0.3)
        self.controller.press("a", delay=0.3)
        self.controller.press("w", delay=0.3)
        time.sleep(0.5)
