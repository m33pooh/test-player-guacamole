import time
from typing import Dict, List, Any
from maple.app.controller.input_driver import GuacamoleInputDriver
from maple.app.navigation.pathfinder import Pathfinder


class LootCycleEngine:
    """
    15-Cycle Multi-Station Loot & Refresh Engine.
    Routes through ALL summon stations (Erda Fountain, Sol Janus, etc.) sequentially
    during cycles 14-15 before returning to kill-focus rotation.
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
        self.current_station_idx = 0

        summons = map_config.get("summon_positions", {})
        if isinstance(summons, dict):
            self.summon_locations = list(summons.values())
        elif isinstance(summons, list):
            self.summon_locations = summons
        else:
            default_pos = map_config.get("summon_position")
            if default_pos:
                self.summon_locations = [default_pos]

        self.is_looting = False

    def on_waypoint_loop_completed(self):
        self.current_cycle = (self.current_cycle % self.total_cycle_count) + 1
        was_looting = self.is_looting
        self.is_looting = (self.current_cycle >= self.loot_cycles_start)
        if self.is_looting and not was_looting:
            self.current_station_idx = 0
            print(
                f"[LootCycleEngine] Cycle #{self.current_cycle}/{self.total_cycle_count} "
                f"[LOOT & REFRESH PHASE ACTIVE - {len(self.summon_locations)} stations]",
                flush=True,
            )
        else:
            print(f"[LootCycleEngine] Cycle #{self.current_cycle}/{self.total_cycle_count} [KILL FOCUS PHASE]", flush=True)

    def execute_loot_sweep(self, player_pos: List[int]) -> str:
        if not player_pos or not self.summon_locations:
            return "ALL_STATIONS_LOOTED"

        if self.current_station_idx >= len(self.summon_locations):
            self.current_station_idx = 0
            return "ALL_STATIONS_LOOTED"

        px, py = player_pos[0], player_pos[1]
        target_s = self.summon_locations[self.current_station_idx]
        sx, sy = target_s[0], target_s[1]
        dist = ((px - sx) ** 2 + (py - sy) ** 2) ** 0.5

        if dist <= 10:
            print(
                f"[LootCycleEngine] Swept station #{self.current_station_idx+1} at ({sx}, {sy}). Refreshing summon...",
                flush=True,
            )
            self.driver.press_combo(["ArrowDown", "s"])
            time.sleep(0.1)
            self.current_station_idx += 1
            if self.current_station_idx >= len(self.summon_locations):
                self.current_station_idx = 0
                return "ALL_STATIONS_LOOTED"
            return f"STATION_{self.current_station_idx}_LOOTED"

        steps = self.pathfinder.plan_path(px, py, sx, sy)
        if steps:
            s = steps[0]
            act = s.get("action")
            if act == "FLASH_JUMP":
                self.driver.flash_jump(direction=s.get("direction", "right"))
            elif act == "DOWN_JUMP":
                self.driver.down_jump()
            elif act == "ROPE_LIFT":
                self.driver.rope_lift()
            else:
                self.driver.walk(direction=s.get("direction", "right"), duration=0.25)
        return f"ROUTING_TO_STATION_{self.current_station_idx+1}"
