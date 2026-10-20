import time
from typing import Dict, List, Optional, Any
import numpy as np
from maple.app.controller.input_driver import GuacamoleInputDriver
from maple.app.navigation.pathfinder import Pathfinder
from maple.app.vision.rune_solver import RuneSolver


class RuneSolvingEngine:
    """
    Rune Navigation and Arrow Solving Engine.
    Coordinates navigating to the rune location, pressing interact (Spacebar),
    detecting arrow directions via RuneSolver, and inputting the solution sequence.
    """

    def __init__(
        self,
        driver: GuacamoleInputDriver,
        pathfinder: Pathfinder,
        rune_solver: Optional[RuneSolver] = None,
        interact_key: str = "Space",
    ):
        self.driver = driver
        self.pathfinder = pathfinder
        self.solver = rune_solver or RuneSolver()
        self.interact_key = interact_key

        self.last_rune_solved_time = 0.0
        self.rune_cooldown_sec = 900.0  # 15 minutes MapleStory rune cooldown

        self.phase = "NAVIGATE"  # "NAVIGATE", "INTERACT", "SOLVE", "VERIFY"
        self.phase_start_time = 0.0

    def can_solve_rune(self) -> bool:
        """
        Checks if player is off rune cooldown.
        """
        return (time.time() - self.last_rune_solved_time) > self.rune_cooldown_sec

    def reset(self):
        self.phase = "NAVIGATE"
        self.phase_start_time = time.time()

    def step(
        self,
        player_pos: List[int],
        rune_pos: List[int],
        frame: np.ndarray,
    ) -> Dict[str, Any]:
        """
        Advances the Rune Solving sequence.
        Returns status dictionary: {"status": "IN_PROGRESS" | "SUCCESS" | "FAILED", "phase": ...}
        """
        if not rune_pos or not player_pos:
            return {"status": "FAILED", "reason": "Missing coordinate"}

        now = time.time()
        px, py = player_pos[0], player_pos[1]
        rx, ry = rune_pos[0], rune_pos[1]
        dist = ((px - rx) ** 2 + (py - ry) ** 2) ** 0.5

        # PHASE 1: NAVIGATE TO RUNE
        if self.phase == "NAVIGATE":
            if dist <= 8:
                print(f"[RuneSolving] Arrived at Rune position ({rx}, {ry}). Initiating interaction...", flush=True)
                self.phase = "INTERACT"
                self.phase_start_time = now
                return {"status": "IN_PROGRESS", "phase": "INTERACT"}

            # Move towards Rune
            steps = self.pathfinder.plan_path(px, py, rx, ry)
            if steps:
                step = steps[0]
                action = step.get("action")
                direction = step.get("direction", "right")
                if action == "FLASH_JUMP":
                    self.driver.flash_jump(direction=direction)
                elif action == "WALK":
                    self.driver.walk(direction=direction, duration=0.2)
                elif action == "DOWN_JUMP":
                    self.driver.down_jump()
                elif action == "ROPE_LIFT":
                    self.driver.rope_lift()
            else:
                # Direct walk
                direction = "right" if rx > px else "left"
                self.driver.walk(direction=direction, duration=0.25)

            return {"status": "IN_PROGRESS", "phase": "NAVIGATE", "dist": dist}

        # PHASE 2: INTERACT (PRESS SPACEBAR)
        elif self.phase == "INTERACT":
            print(f"[RuneSolving] Pressing interact key ({self.interact_key})...", flush=True)
            self.driver.press_key(self.interact_key, duration=0.08)
            time.sleep(0.5)
            self.phase = "SOLVE"
            self.phase_start_time = time.time()
            return {"status": "IN_PROGRESS", "phase": "SOLVE"}

        # PHASE 3: SOLVE 4-ARROW PUZZLE
        elif self.phase == "SOLVE":
            arrow_keys = self.solver.solve_arrows(frame)
            if len(arrow_keys) == 4:
                print(f"[RuneSolving] Detected Arrow Sequence: {arrow_keys}", flush=True)
                self.driver.press_sequence(arrow_keys, inter_delay=0.18)
                self.last_rune_solved_time = time.time()
                self.phase = "VERIFY"
                return {"status": "IN_PROGRESS", "phase": "VERIFY", "arrows": arrow_keys}
            else:
                if (now - self.phase_start_time) > 4.0:
                    print("[RuneSolving Warning] Timeout waiting for arrow prompt.", flush=True)
                    return {"status": "FAILED", "reason": "Timeout"}
                return {"status": "IN_PROGRESS", "phase": "WAITING_PROMPT"}

        # PHASE 4: VERIFY
        elif self.phase == "VERIFY":
            print("[RuneSolving] Rune sequence completed successfully! Returning to rotation.", flush=True)
            self.last_rune_solved_time = time.time()
            return {"status": "SUCCESS"}

        return {"status": "FAILED"}
