import time
from typing import Dict, List, Optional, Any
from maple.app.controller.input_driver import GuacamoleInputDriver
from maple.app.navigation.pathfinder import Pathfinder
from maple.app.navigation.movement_macros import MovementMacros
from maple.app.state_machine.loot_cycle import LootCycleEngine
from maple.app.state_machine.archetypes.teleporter_fsm import TeleporterFSM
from maple.app.state_machine.archetypes.projectile_fsm import ProjectileFSM
from maple.app.state_machine.archetypes.summoner_fsm import SummonerFSM
from maple.app.state_machine.archetypes.sweeper_fsm import SweeperFSM


class RotationFarmEngine:
    """
    Combat & Map Rotation execution engine.
    Supports Class Archetypes (maplev2.md Section 3):
    - TELEPORTER (Mages/Bishop): Teleport casting, vertical reach jumps
    - PROJECTILE (Night Lord/Assassins): Centralized platform jumping & bouncing marks
    - SUMMONER (Lara/Corsair): Multi-summon deployment and Dragon Vein eruptions
    - SWEEPER (Buccaneer/Adele): High-speed Super Jumps & gauge aura management
    Also manages 15-cycle Loot & Refresh passes (Section 5.3).
    """

    def __init__(
        self,
        driver: GuacamoleInputDriver,
        pathfinder: Pathfinder,
        map_config: Dict[str, Any],
        class_config: Dict[str, Any],
    ):
        self.driver = driver
        self.pathfinder = pathfinder
        self.map_config = map_config
        self.class_config = class_config

        self.waypoints: List[Dict[str, Any]] = map_config.get("waypoints", [])
        self.current_waypoint_idx = 0

        self.macros = MovementMacros(driver)
        self.loot_engine = LootCycleEngine(driver, pathfinder, map_config)

        # Instantiate class archetype engine
        archetype = class_config.get("archetype", "PROJECTILE").upper()
        if "TELEPORT" in archetype:
            self.archetype_engine = TeleporterFSM(driver, self.macros, pathfinder, class_config, map_config)
        elif "SUMMON" in archetype or "LARA" in archetype:
            self.archetype_engine = SummonerFSM(driver, self.macros, pathfinder, class_config, map_config)
        elif "SWEEP" in archetype or "BUCCANEER" in archetype or "ADELE" in archetype:
            self.archetype_engine = SweeperFSM(driver, self.macros, pathfinder, class_config, map_config)
        else:
            self.archetype_engine = ProjectileFSM(driver, self.macros, pathfinder, class_config, map_config)

        # Buffs tracker
        self.buffs = class_config.get("buffs", {})
        self.buff_timers: Dict[str, float] = {}

    def get_current_waypoint(self) -> Optional[Dict[str, Any]]:
        if not self.waypoints:
            return None
        return self.waypoints[self.current_waypoint_idx]

    def advance_waypoint(self):
        if self.waypoints:
            prev_idx = self.current_waypoint_idx
            self.current_waypoint_idx = (self.current_waypoint_idx + 1) % len(self.waypoints)
            # Full loop completed
            if self.current_waypoint_idx == 0 and prev_idx == len(self.waypoints) - 1:
                self.loot_engine.on_waypoint_loop_completed()

    def execute_rotation_step(
        self,
        player_pos: List[int],
        class_state: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Executes one step in the farming rotation cycle.
        """
        if not player_pos or len(player_pos) < 2:
            return "NO_PLAYER_POS"

        px, py = player_pos[0], player_pos[1]
        now = time.time()

        # 1. Cast buffs if off cooldown
        for buff_name, b_info in self.buffs.items():
            b_key = b_info.get("key")
            b_cd = b_info.get("cooldown", b_info.get("cooldown_sec", 180.0))
            last_t = self.buff_timers.get(buff_name, 0.0)
            if (now - last_t) > b_cd and b_key:
                print(f"[RotationFarm] Casting buff {buff_name} ({b_key})...", flush=True)
                self.driver.press_key(b_key)
                self.buff_timers[buff_name] = now
                time.sleep(0.08)

        # 2. Check if currently in Loot Cycle (cycles 14-15)
        if self.loot_engine.is_looting:
            loot_act = self.loot_engine.execute_loot_sweep(player_pos)
            if loot_act == "LOOTED_STATION":
                # Return to regular rotation after sweeping
                self.loot_engine.is_looting = False
            return f"LOOT_CYCLE_{loot_act}"

        # 3. Navigate towards current waypoint
        wp = self.get_current_waypoint()
        if not wp:
            return "NO_WAYPOINTS"

        tx, ty = wp["x"], wp["y"]
        dist = ((tx - px) ** 2 + (ty - py) ** 2) ** 0.5

        if dist <= 12:
            print(f"[RotationFarm] Reached waypoint #{self.current_waypoint_idx+1} at ({tx}, {ty})", flush=True)
            self.advance_waypoint()
            return "WAYPOINT_REACHED"

        # 4. Delegate to Class Archetype Engine
        if hasattr(self.archetype_engine, "execute_step"):
            try:
                # Some archetypes accept class_state
                import inspect
                sig = inspect.signature(self.archetype_engine.execute_step)
                if len(sig.parameters) >= 3:
                    return self.archetype_engine.execute_step(player_pos, wp, class_state)
                else:
                    return self.archetype_engine.execute_step(player_pos, wp)
            except Exception as e:
                print(f"[RotationFarm Warning] Archetype execution exception: {e}", flush=True)

        return "ROTATION_STEP"
