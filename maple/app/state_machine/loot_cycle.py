import time
from typing import Dict, List, Optional, Any
from maple.app.controller.input_driver import GuacamoleInputDriver
from maple.app.navigation.pathfinder import Pathfinder


class LootCycleEngine:
    """
    15-Cycle Loot & Refresh Engine.
    Implements Section 5.3 of maplev2.md:
    - Cycle 1 - 13 (Kill Focus): High-tempo mobbing in core zone without detouring.
    - Cycle 14 - 15 (Loot & Refresh Cycle): Routes to Summon stations (Erda Fountain, Sol Janus)
      to sweep all accumulated Meso bags before the 120s despawn window, re-casting summons.
    """

    def __init__(
        self,
        driver: GuacamoleInputDriver,
        pathfinder: Pathfinder,
        map_config: Dict[str, Any],
        total_cycle_count: int = 15,
        loot_cycles_start: int = 14,
    ):
        self.driver = driver
        self.pathfinder = pathfinder
        self.map_config = map_config
        self.total_cycle_count = total_cycle_count
        self.loot_cycles_start = loot_cycles_start

        self.current_cycle = 1
        self.summon_locations: List[List[int]] = []

        # Load summon stations from map config
        summons = map_config.get("summon_positions", {})
        if isinstance(summons, dict):
            self.summon_locations = list(summons.values())
        elif isinstance(summons, list):
            self.summon_locations = summons
        else:
            self.summon_locations = [map_config.get("summon_position", [64, 112])]

        self.is_looting = False

    def on_waypoint_loop_completed(self):
        """
        Called when character completes 1 full waypoint cycle.
        """
        self.current_cycle = (self.current_cycle % self.total_cycle_count) + 1
        self.is_looting = (self.current_cycle >= self.loot_cycles_start)
        if self.is_looting:
            print(f"[LootCycleEngine] Cycle #{self.current_cycle}/{self.total_cycle_count} [LOOT & REFRESH PHASE ACTIVE]", flush=True)
        else:
            print(f"[LootCycleEngine] Cycle #{self.current_cycle}/{self.total_cycle_count} [KILL FOCUS PHASE]", flush=True)

    def execute_loot_sweep(self, player_pos: List[int]) -> str:
        """
        Routes character through summon locations to collect Meso bags.
        """
        if not player_pos or not self.summon_locations:
            return "NO_SUMMON_TARGETS"

        px, py = player_pos[0], player_pos[1]
        # Find nearest summon station not yet reached
        target_s = self.summon_locations[0]
        sx, sy = target_s[0], target_s[1]
        dist = ((px - sx) ** 2 + (py - sy) ** 2) ** 0.5

        if dist < 8:
            print(f"[LootCycleEngine] Sweeping meso bags at summon station ({sx}, {sy}). Refreshing summon...", flush=True)
            self.driver.press_combo(["ArrowDown", "w"])  # Refresh summon
            time.sleep(0.1)
            return "LOOTED_STATION"

        steps = self.pathfinder.plan_path(px, py, sx, sy)
        if steps:
            s = steps[0]
            if s.get("action") == "FLASH_JUMP":
                self.driver.flash_jump(direction=s.get("direction", "right"))
            elif s.get("action") == "DOWN_JUMP":
                self.driver.down_jump()
            elif s.get("action") == "ROPE_LIFT":
                self.driver.rope_lift()
            else:
                self.driver.walk(direction=s.get("direction", "right"), duration=0.25)
        return "ROUTING_TO_LOOT"
