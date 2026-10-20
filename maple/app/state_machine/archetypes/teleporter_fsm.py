import time
from typing import Dict, List, Optional, Any
from maple.app.controller.input_driver import GuacamoleInputDriver
from maple.app.navigation.movement_macros import MovementMacros
from maple.app.navigation.pathfinder import Pathfinder


class TeleporterFSM:
    """
    Class Archetype: The Teleporters (Bishop, Arch Mage, Luminous, Battle Mage).
    Farming characteristics:
    - Teleport Casting (Animation canceling attack + teleport).
    - Can teleport vertically between platforms without Rope Lift if distance < reach.
    - Large stationary summons (Fountain of Vengeance, Erda Shower) covering opposite map wings.
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

        # Movement params
        m_cfg = class_config.get("movement", {})
        self.teleport_key = m_cfg.get("teleport_key", "Shift")
        self.h_reach = m_cfg.get("horizontal_distance_px", 22)
        self.v_reach = m_cfg.get("vertical_reach_px", 18)

        # Skill keys
        skills = class_config.get("skills", {})
        mobbing = skills.get("main_mobbing", {})
        self.mobbing_key = mobbing.get("key", "Ctrl") if isinstance(mobbing, dict) else skills.get("mobbing", "Ctrl")

        self.summons = skills.get("summons", [])
        self.summon_timers: Dict[str, float] = {}

    def execute_step(self, player_pos: List[int], target_wp: Dict[str, Any]) -> str:
        if not player_pos:
            return "NO_PLAYER_POS"

        px, py = player_pos[0], player_pos[1]
        tx, ty = target_wp["x"], target_wp["y"]
        dx = tx - px
        dy = ty - py
        now = time.time()

        # 1. Manage Summon skills (Fountain of Vengeance, Erda Fountain, Bahamut)
        for s in self.summons:
            s_name = s.get("name", "summon")
            s_key = s.get("key", "a")
            s_cd = s.get("cooldown_sec", 60.0)
            last_t = self.summon_timers.get(s_name, 0.0)
            if (now - last_t) > s_cd:
                print(f"[TeleporterFSM] Casting summon: {s_name} ({s_key})...", flush=True)
                self.driver.press_combo(["ArrowDown", s_key])
                self.summon_timers[s_name] = now
                return f"CAST_SUMMON_{s_name}"

        # 2. Check vertical teleport reach
        if abs(dy) <= self.v_reach and abs(dx) < 15:
            vert_dir = "up" if dy < 0 else "down"
            print(f"[TeleporterFSM] Vertical Teleport {vert_dir} towards platform Y={ty}", flush=True)
            self.macros.teleport_cast(direction="right", teleport_key=self.teleport_key, attack_key=self.mobbing_key, vertical=vert_dir)
            return f"TELEPORT_{vert_dir.upper()}"

        # 3. Horizontal Teleport Casting
        direction = "right" if dx > 0 else "left"
        self.macros.teleport_cast(direction=direction, teleport_key=self.teleport_key, attack_key=self.mobbing_key)
        return f"TELEPORT_CAST_{direction.upper()}"
