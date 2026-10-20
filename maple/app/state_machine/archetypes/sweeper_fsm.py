import time
from typing import Dict, List, Optional, Any
from maple.app.controller.input_driver import GuacamoleInputDriver
from maple.app.navigation.movement_macros import MovementMacros
from maple.app.navigation.pathfinder import Pathfinder


class SweeperFSM:
    """
    Class Archetype: The Active Sweepers & Gauge Managers (Buccaneer, Adele, Dawn Warrior).
    """

    def __init__(
        self,
        driver: GuacamoleInputDriver,
        macros: MovementMacros,
        pathfinder: Pathfinder,
        class_config: Dict[str, Any],
        map_config: Dict[str, Any],
    ):
        self.driver = driver
        self.macros = macros
        self.pathfinder = pathfinder
        self.class_config = class_config
        self.map_config = map_config

        movement = class_config.get("movement", {})
        skills = class_config.get("skills", {})
        mobbing = skills.get("main_mobbing", {})

        self.jump_key = movement.get("jump_key") or skills.get("jump", "Alt")
        self.dash_key = movement.get("dash_key") or skills.get("dash", "Shift")
        self.mobbing_key = mobbing.get("key", "q") if isinstance(mobbing, dict) else skills.get("mobbing", "q")
        self.gauge_skill_key = skills.get("gauge_skill", "w")

        self.last_gauge_cast = 0.0

    def execute_step(
        self,
        player_pos: List[int],
        target_wp: Dict[str, Any],
        class_state: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not player_pos:
            return "NO_PLAYER_POS"

        px, py = player_pos[0], player_pos[1]
        tx, ty = target_wp["x"], target_wp["y"]
        dx = tx - px
        now = time.time()

        # 1. Manage Gauge Skill (Lord of the Deep / Order)
        gauge_ratio = class_state.get("gauge_ratio", 1.0) if class_state else 1.0
        lord_active = class_state.get("lord_of_deep_active", False) if class_state else False

        if gauge_ratio > 0.50 and not lord_active and (now - self.last_gauge_cast) > 6.0:
            print(f"[SweeperFSM] Gauge healthy ({gauge_ratio*100:.0f}%), activating gauge skill ({self.gauge_skill_key})...", flush=True)
            self.driver.press_key(self.gauge_skill_key)
            self.last_gauge_cast = now

        # 2. High-speed Super Jump Glide
        direction = "right" if dx > 0 else "left"
        self.macros.buccaneer_super_jump(direction=direction, dash_key=self.dash_key, jump_key=self.jump_key)
        self.driver.press_key(self.mobbing_key)

        return f"SUPER_JUMP_SWEEP_{direction.upper()}"
