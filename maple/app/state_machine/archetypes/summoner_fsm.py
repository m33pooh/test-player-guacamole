import time
from typing import Dict, List, Optional, Any
from maple.app.controller.input_driver import GuacamoleInputDriver
from maple.app.navigation.movement_macros import MovementMacros
from maple.app.navigation.pathfinder import Pathfinder


class SummonerFSM:
    """
    Class Archetype: The Micro-Summon & Area Controllers (Lara, Corsair, Kanna).
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
        self.mobbing_key = mobbing.get("key", "q") if isinstance(mobbing, dict) else skills.get("mobbing", "q")
        self.eruption_key = skills.get("eruption", "w")
        self.manifestation_key = skills.get("manifestation", "e")

        strategy = class_config.get("strategy", {})
        self.last_refresh_time = 0.0
        self.refresh_interval = float(strategy.get("vein_refresh_interval_sec", 16.0))

    def execute_step(
        self,
        player_pos: List[int],
        target_wp: Dict[str, Any],
        class_state: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not player_pos:
            return "NO_PLAYER_POS"

        px, py = player_pos[0], player_pos[1]
        now = time.time()

        # 1. Check if nearby Dragon Vein can be erupted (Lara)
        if class_state and "detected_veins" in class_state:
            veins = class_state.get("detected_veins", [])
            for v in veins:
                if (now - self.last_refresh_time) > self.refresh_interval:
                    print(f"[SummonerFSM] Standing on Dragon Vein ({v['type']}), casting Eruption ({self.eruption_key})...", flush=True)
                    self.driver.press_key(self.eruption_key)
                    self.last_refresh_time = now
                    return f"ERUPTION_{v['type'].upper()}"

        # 2. Regular Waypoint Navigation & Sprinkling (Mobbing)
        tx, ty = target_wp["x"], target_wp["y"]
        dx = tx - px
        direction = "right" if dx > 0 else "left"

        if abs(dx) > 28:
            self.macros.flash_jump_attack(direction=direction, jump_key=self.jump_key, attack_key=self.mobbing_key)
        else:
            self.driver.walk(direction=direction, duration=0.20)
            self.driver.press_key(self.mobbing_key)
        return "SUMMONER_SWEEP"
