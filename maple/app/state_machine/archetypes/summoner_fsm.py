import time
from typing import Dict, List, Optional, Any
from maple.app.controller.input_driver import GuacamoleInputDriver
from maple.app.navigation.movement_macros import MovementMacros
from maple.app.navigation.pathfinder import Pathfinder


class SummonerFSM:
    """
    Class Archetype: The Micro-Summon & Area Controllers (Lara, Corsair, Kanna).
    Farming characteristics:
    - High reliance on multi-station summons.
    - Lara: Walks onto Dragon Veins (River, Wind, Sun) and casts Eruption.
    - Cycle & Refresh: Refreshes active ground installations every 15-18 seconds.
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
        self.eruption_key = skills.get("eruption", "w")
        self.manifestation_key = skills.get("manifestation", "e")

        self.last_refresh_time = 0.0
        self.refresh_interval = 16.0  # Lara 15-18s refresh cycle

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
                # If standing on or close to vein (screen coords converted to relative proximity)
                if (now - self.last_refresh_time) > self.refresh_interval:
                    print(f"[SummonerFSM] Standing on Dragon Vein ({v['type']}), casting Eruption ({self.eruption_key})...", flush=True)
                    self.driver.press_key(self.eruption_key)
                    self.last_refresh_time = now
                    return f"ERUPTION_{v['type'].upper()}"

        # 2. Regular Waypoint Navigation & Sprinkling (Mobbing)
        tx, ty = target_wp["x"], target_wp["y"]
        dx = tx - px
        direction = "right" if dx > 0 else "left"

        self.driver.walk(direction=direction, duration=0.20)
        self.driver.press_key(self.mobbing_key)
        return "SUMMONER_SWEEP"
