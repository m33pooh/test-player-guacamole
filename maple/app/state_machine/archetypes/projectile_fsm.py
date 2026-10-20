import time
from typing import Dict, List, Optional, Any
from maple.app.controller.input_driver import GuacamoleInputDriver
from maple.app.navigation.movement_macros import MovementMacros
from maple.app.navigation.pathfinder import Pathfinder


class ProjectileFSM:
    """
    Class Archetype: The Projectile & Mark Assassins (Night Lord, Night Walker, Wind Archer).
    Farming characteristics:
    - High-mobility Flash Jump with bouncing projectile marks (Assassin's Mark / Shadow Bat).
    - Centralized rotation: Dominates middle platform while Summons cover map corners.
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

        skills = class_config.get("skills", {})
        self.jump_key = skills.get("jump", "Alt")
        self.mobbing_key = skills.get("mobbing", "q")
        self.rope_lift_key = skills.get("rope_lift", "v")
        self.summon_key = skills.get("summon", "w")
        self.summon_cd = class_config.get("summon_cooldown", 60.0)

        self.last_summon_time = 0.0

    def execute_step(self, player_pos: List[int], target_wp: Dict[str, Any]) -> str:
        if not player_pos:
            return "NO_PLAYER_POS"

        px, py = player_pos[0], player_pos[1]
        tx, ty = target_wp["x"], target_wp["y"]
        dx = tx - px
        now = time.time()

        # 1. Maintain peripheral summon
        if (now - self.last_summon_time) > self.summon_cd:
            print(f"[ProjectileFSM] Dropping peripheral summon ({self.summon_key})...", flush=True)
            self.driver.press_combo(["ArrowDown", self.summon_key])
            self.last_summon_time = now
            return "SUMMON_DEPLOYED"

        # 2. Flash Jump Attack
        direction = "right" if dx > 0 else "left"
        self.macros.flash_jump_attack(
            direction=direction,
            jump_key=self.jump_key,
            attack_key=self.mobbing_key,
        )
        return f"FLASH_JUMP_ATTACK_{direction.upper()}"
