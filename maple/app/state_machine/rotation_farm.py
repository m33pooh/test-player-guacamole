import inspect
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
    Supports unified buff parsing across YAML schemas and 2D vertical platform navigation.
    """

    def __init__(
        self,
        driver: GuacamoleInputDriver,
        pathfinder: Pathfinder,
        map_config: Dict[str, Any],
        class_config: Dict[str, Any],
        mob_detector: Optional[Any] = None,
        capture_fn: Optional[Any] = None,
        mob_watcher: Optional[Any] = None,
    ):
        self.driver = driver
        self.pathfinder = pathfinder
        self.map_config = map_config
        self.class_config = class_config
        self.mob_detector = mob_detector
        self.capture_fn = capture_fn
        self.mob_watcher = mob_watcher

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
            self.archetype_engine = ProjectileFSM(
                driver,
                self.macros,
                pathfinder,
                class_config,
                map_config,
                mob_detector=mob_detector,
                capture_fn=capture_fn,
                mob_watcher=mob_watcher,
            )

        # Normalize buffs from either root 'buffs' (dict/list) or 'skills.buffs' (list)
        self.normalized_buffs = self._parse_buffs(class_config)
        self.buff_timers: Dict[str, float] = {}

        # Extract rope lift & jump keys
        skills = class_config.get("skills", {})
        movement = class_config.get("movement", {})
        self.rope_lift_key = movement.get("rope_lift_key") or skills.get("rope_lift", "v")
        self.jump_key = movement.get("jump_key") or skills.get("jump", "Alt")

    def _parse_buffs(self, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw_buffs = cfg.get("buffs") or cfg.get("skills", {}).get("buffs", [])
        parsed = []
        if isinstance(raw_buffs, dict):
            for b_name, b_data in raw_buffs.items():
                parsed.append({
                    "name": b_name,
                    "key": b_data.get("key"),
                    "cooldown": float(b_data.get("cooldown", b_data.get("cooldown_sec", 180.0))),
                })
        elif isinstance(raw_buffs, list):
            for item in raw_buffs:
                if isinstance(item, dict):
                    parsed.append({
                        "name": item.get("name", "buff"),
                        "key": item.get("key"),
                        "cooldown": float(item.get("cooldown_sec", item.get("cooldown", 180.0))),
                    })
        return parsed

    def get_current_waypoint(self) -> Optional[Dict[str, Any]]:
        if not self.waypoints:
            return None
        return self.waypoints[self.current_waypoint_idx]

    def advance_waypoint(self):
        if self.waypoints:
            prev_idx = self.current_waypoint_idx
            self.current_waypoint_idx = (self.current_waypoint_idx + 1) % len(self.waypoints)
            if self.current_waypoint_idx == 0 and prev_idx == len(self.waypoints) - 1:
                self.loot_engine.on_waypoint_loop_completed()

    def execute_rotation_step(
        self,
        player_pos: List[int],
        class_state: Optional[Dict[str, Any]] = None,
        frame: Optional[Any] = None,
    ) -> str:
        if not player_pos or len(player_pos) < 2:
            return "NO_PLAYER_POS"

        px, py = player_pos[0], player_pos[1]
        now = time.time()

        # 1. Cast buffs if off cooldown
        for b in self.normalized_buffs:
            b_name = b["name"]
            b_key = b["key"]
            b_cd = b["cooldown"]
            last_t = self.buff_timers.get(b_name, 0.0)
            if b_key and (now - last_t) > b_cd:
                print(f"[RotationFarm] Casting buff {b_name} ({b_key})...", flush=True)
                self.driver.press_key(b_key)
                self.buff_timers[b_name] = now
                time.sleep(0.08)

        # 2. Check if currently in Loot Cycle (cycles 14-15)
        if self.loot_engine.is_looting:
            loot_act = self.loot_engine.execute_loot_sweep(player_pos)
            if loot_act == "ALL_STATIONS_LOOTED":
                self.loot_engine.is_looting = False
            return f"LOOT_CYCLE_{loot_act}"

        # 3. Check current waypoint distance
        wp = self.get_current_waypoint()
        if not wp:
            return "NO_WAYPOINTS"

        tx, ty = wp["x"], wp["y"]
        dist = ((tx - px) ** 2 + (ty - py) ** 2) ** 0.5
        is_turret = wp.get("action") == "TURRET_SHOOT" or bool(self.map_config.get("anchor_spot"))

        if not is_turret and dist <= 12:
            print(f"[RotationFarm] Reached waypoint #{self.current_waypoint_idx+1} at ({tx}, {ty})", flush=True)
            self.advance_waypoint()
            return "WAYPOINT_REACHED"

        # 4. Vertical Platform Pathfinding Check (Rope Lift / Down+Jump)
        # If player is on a different vertical platform level (|ty - py| > 15), use Pathfinder first
        if abs(ty - py) > 15 and not isinstance(self.archetype_engine, TeleporterFSM):
            steps = self.pathfinder.plan_path(px, py, tx, ty)
            if steps:
                first_step = steps[0]
                act = first_step.get("action")
                if act == "ROPE_LIFT":
                    print(f"[RotationFarm] Ascending platform via Rope Lift ({self.rope_lift_key}) -> target Y={ty}", flush=True)
                    self.macros.rope_lift(rope_key=self.rope_lift_key)
                    time.sleep(0.6)
                    return "VERTICAL_ROPE_LIFT"
                elif act == "DOWN_JUMP":
                    print(f"[RotationFarm] Dropping down platform via Down+Jump -> target Y={ty}", flush=True)
                    self.macros.down_jump(jump_key=self.jump_key)
                    time.sleep(0.35)
                    return "VERTICAL_DOWN_JUMP"

        # 5. Delegate Horizontal Combat & Movement to Class Archetype Engine
        if hasattr(self.archetype_engine, "execute_step"):
            try:
                sig = inspect.signature(self.archetype_engine.execute_step)
                params = sig.parameters
                if "frame" in params:
                    return self.archetype_engine.execute_step(player_pos, wp, class_state, frame=frame)
                elif len(params) >= 3:
                    return self.archetype_engine.execute_step(player_pos, wp, class_state)
                else:
                    return self.archetype_engine.execute_step(player_pos, wp)
            except Exception as e:
                print(f"[RotationFarm Warning] Archetype execution exception: {e}", flush=True)

        return "ROTATION_STEP"
