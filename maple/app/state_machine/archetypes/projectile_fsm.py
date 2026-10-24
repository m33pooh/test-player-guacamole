import time
from typing import Dict, List, Optional, Any, Callable, Tuple
import numpy as np
from maple.app.controller.input_driver import GuacamoleInputDriver
from maple.app.navigation.movement_macros import MovementMacros
from maple.app.navigation.pathfinder import Pathfinder
from maple.app.vision.mob_detector import MobDetector
from maple.app.vision.minimap_tracker import MinimapTracker


class ProjectileFSM:
    """
    Class Archetype: The Projectile & Bow Archetype (Bowman, Hunter, Crossbowman, Night Lord).
    Farming characteristics:
    - Long-range projectile attacks with continuous fire cadence (~300ms).
    - Monster HP calculation: Monitors green HP bar width (0-76px) in real-time.
    - Continuous combat loop: Fires uninterrupted until monster HP reaches 0 / bar disappears.
    - Post-kill immediate looting before advancing to next patrol waypoint.
    """

    def __init__(
        self,
        driver: GuacamoleInputDriver,
        macros: MovementMacros,
        pathfinder: Pathfinder,
        class_config: Dict[str, Any],
        map_config: Dict[str, Any],
        mob_detector: Optional[MobDetector] = None,
        capture_fn: Optional[Callable[[], Optional[np.ndarray]]] = None,
        mob_watcher: Optional[Any] = None,
    ):
        self.driver = driver
        self.macros = macros
        self.pathfinder = pathfinder
        self.class_config = class_config
        self.map_config = map_config
        self.mob_detector = mob_detector or MobDetector()
        self.capture_fn = capture_fn
        self.mob_watcher = mob_watcher

        skills = class_config.get("skills", {})
        self.jump_key = skills.get("jump", "Alt")
        self.mobbing_key = skills.get("mobbing", "x")
        self.attack_key = skills.get("attack", "x")
        self.skill_key = skills.get("skill", "c")
        self.loot_key = skills.get("loot", "z")
        self.rope_lift_key = skills.get("rope_lift", "v")
        self.summon_key = skills.get("summon", "w")
        self.summon_cd = class_config.get("summon_cooldown", 60.0)
        self.skill_cd = float(class_config.get("strategy", {}).get("skill_cooldown", 30.0))

        self.last_summon_time = 0.0
        self.last_skill_time = 0.0

        # Stationary Turret & Timed Loot Sweep Settings
        self.anchor_spot = map_config.get("anchor_spot")
        self.platform_bounds = map_config.get("platform_bounds", {"min_x": 102, "max_x": 142, "y": 80})
        self.player_screen_center = tuple(map_config.get("player_screen_center", [1065, 700]))
        self.island_reach = map_config.get("island_reach", {})
        self.reach_left = int(self.island_reach.get("left", 605))
        self.reach_right = int(self.island_reach.get("right", 260))
        self.loot_interval = float(map_config.get("loot_interval_sec", 60.0))
        self.last_loot_sweep_time = time.time()
        self.turret_facing = "left"
        self.empty_shot_streak = {"left": 0, "right": 0}
        self.tracker = MinimapTracker()
        self.bench_mounted = False

    def capture_frame(self) -> Optional[np.ndarray]:
        if self.mob_watcher:
            f = self.mob_watcher.get_latest_frame()
            if f is not None:
                return f
        if self.capture_fn:
            try:
                return self.capture_fn()
            except Exception:
                return None
        return None

    def execute_platform_loot_sweep(self, player_pos: List[int]):
        """
        Calculates hold duration from minimap distance (px) and holds the direction key down
        continuously while tapping loot (Z) to sweep across platform, then returns
        to anchor and jumps back up.
        """
        anchor_x = self.anchor_spot[0] if self.anchor_spot else 126
        px = player_pos[0] if player_pos and len(player_pos) >= 1 else anchor_x
        # Speed calibration: ~18-20 minimap pixels per second -> ~0.055s per minimap pixel
        SEC_PER_PX = 0.055

        loot_left = self.platform_bounds.get("loot_left", self.platform_bounds.get("min_x", 95) + 12)
        loot_right = self.platform_bounds.get("loot_right", self.platform_bounds.get("max_x", 155) - 12)

        print(f"[Loot Sweep] Starting timed hold platform sweep from px={px} across [{loot_left}..{loot_right}] (Interval: {self.loot_interval:.0f}s)...", flush=True)

        # 1. Calculate time to walk Left to loot zone
        dist_left = max(0, px - loot_left)
        dur_left = max(0.35, min(2.50, dist_left * SEC_PER_PX))
        print(f"[Loot Sweep] Walking LEFT (hold {dur_left:.2f}s, dist={dist_left}px) to collect left loot...", flush=True)
        self.driver.walk_and_loot("left", duration=dur_left, loot_key=self.loot_key)
        for _ in range(3):
            self.driver.tap_key(self.loot_key)
            time.sleep(0.06)

        # 2. Calculate time to walk Right across platform to loot zone
        dist_right = max(0, loot_right - loot_left)
        dur_right = max(0.80, min(3.50, dist_right * SEC_PER_PX))
        print(f"[Loot Sweep] Walking RIGHT (hold {dur_right:.2f}s, dist={dist_right}px) to collect right loot...", flush=True)
        self.driver.walk_and_loot("right", duration=dur_right, loot_key=self.loot_key)
        for _ in range(3):
            self.driver.tap_key(self.loot_key)
            time.sleep(0.06)

        # 3. Closed-loop return to bench anchor footprint [124..127]
        print(f"[Loot Sweep] Navigating back to bench anchor [{anchor_x}]...", flush=True)
        t_start = time.time()
        while (time.time() - t_start) < 3.0:
            cur_frame = self.capture_frame()
            if cur_frame is not None:
                m_state = self.tracker.track(cur_frame)
                cur_pos = m_state.get("player_pos")
                if cur_pos:
                    cpx = cur_pos[0]
                    if abs(cpx - anchor_x) <= 2:
                        break
                    dir_b = "left" if cpx > anchor_x else "right"
                    self.driver.walk(dir_b, duration=0.14)
            else:
                self.driver.walk("left", duration=0.14)
            time.sleep(0.03)

        # 4. Jump back up onto wooden bench (Alt)!
        print(f"[Loot Sweep] At bench footprint (px={anchor_x}), jumping up onto wooden bench (Alt)...", flush=True)
        jump_key = self.class_config.get("skills", {}).get("jump", "Alt")
        self.driver.tap_key(jump_key)
        time.sleep(0.6)

        # 5. Elevation verification: If still on grass (py >= 84), adjust to 125 and jump again!
        for _ in range(3):
            cur_frame = self.capture_frame()
            if cur_frame is not None:
                m_state = self.tracker.track(cur_frame)
                cur_pos = m_state.get("player_pos")
                if cur_pos and cur_pos[1] <= 78:
                    print(f"[Loot Sweep] Confirmed elevated on bench! pos={cur_pos}", flush=True)
                    break
                elif cur_pos and cur_pos[1] >= 80:
                    print(f"[Loot Sweep] Still on grass (y={cur_pos[1]}), micro-adjusting to {anchor_x} and jumping...", flush=True)
                    cpx = cur_pos[0]
                    if abs(cpx - anchor_x) > 1:
                        self.driver.walk("left" if cpx > anchor_x else "right", duration=0.10)
                    self.driver.tap_key(jump_key)
                    time.sleep(0.5)

        self.last_loot_sweep_time = time.time()
        print(f"[Loot Sweep] Full platform sweep completed! Character secure back at [{anchor_x}].", flush=True)

    def continuous_combat_loop(
        self,
        direction: str,
        initial_target: Optional[Dict[str, Any]] = None,
        max_shots: int = 9,
    ) -> Dict[str, Any]:
        """
        Continuously fires arrows until the target monster HP reaches 0 (dead)
        or the HP bar disappears.
        """
        dir_key = "ArrowRight" if direction == "right" else "ArrowLeft"
        self.driver.press_key(dir_key)
        time.sleep(0.04)

        if initial_target:
            hp_pct = initial_target.get("hp_percent", 100.0)
            w = initial_target.get("width", 76)
            dist_x = initial_target.get("distance_x", 0)
            print(
                f"[Archer Combat] Target engaged ({direction}) | Initial HP: {hp_pct:.1f}% ({w}px) at distance {dist_x}px",
                flush=True,
            )

        last_width = initial_target.get("width", 76) if initial_target else 76
        stagnant_count = 0

        for shot in range(1, max_shots + 1):
            # Fire arrow (rapid bow fire)
            self.driver.tap_key(self.mobbing_key)
            time.sleep(0.15)

            # Capture fresh frame to inspect target HP
            cur_frame = self.capture_frame()
            if cur_frame is None:
                continue

            bars = self.mob_detector.detect_monster_hp_bars(
                cur_frame,
                facing=direction,
                player_center=self.player_screen_center,
                reach_left=self.reach_left,
                reach_right=self.reach_right,
                max_dist_y=150,
            )

            if not bars:
                # Monster HP bar disappeared -> Monster is DEAD!
                print(
                    f"[Archer Combat] Shot #{shot}: Monster DEAD! (0% HP / Bar disappeared)",
                    flush=True,
                )
                return {"status": "KILLED", "shots": shot}

            cur_target = bars[0]
            cur_hp = cur_target["hp_percent"]
            cur_w = cur_target["width"]

            print(
                f"[Archer Combat] Shot #{shot}: Remaining HP = {cur_hp:.1f}% ({cur_w}px)",
                flush=True,
            )

            # Check if HP changed
            if cur_w == last_width:
                stagnant_count += 1
                if stagnant_count >= 2:
                    print(f"[Archer Combat] Monster HP unchanged for 2 shots, target eliminated or out of reach.", flush=True)
                    return {"status": "STAGNANT", "shots": shot}
            else:
                stagnant_count = 0
                last_width = cur_w

        return {"status": "MAX_SHOTS", "shots": max_shots}

    def execute_step(
        self,
        player_pos: List[int],
        target_wp: Dict[str, Any],
        class_state: Optional[Dict[str, Any]] = None,
        frame: Optional[np.ndarray] = None,
    ) -> str:
        if not player_pos:
            return "NO_PLAYER_POS"

        px, py = player_pos[0], player_pos[1]
        now = time.time()

        # 1. Maintain peripheral summon if configured
        if "summon" in self.class_config.get("skills", {}) and (now - self.last_summon_time) > self.summon_cd:
            print(f"[ProjectileFSM] Dropping peripheral summon ({self.summon_key})...", flush=True)
            self.driver.press_combo(["ArrowDown", self.summon_key])
            self.last_summon_time = now
            return "SUMMON_DEPLOYED"

        # 2. Check if in Stationary Turret Mode (stand and shoot left & right)
        is_turret = bool(self.anchor_spot) or target_wp.get("action") == "TURRET_SHOOT"
        if is_turret:
            # 2.1 BENCH POSITION RECOVERY:
            # If monster knockback pushed character off the wooden bench plank onto the grass:
            # Target bench is at x=122.
            # If knocked left (px < 118): Walk right towards bench and jump up through the plank!
            anchor_x = self.anchor_spot[0] if self.anchor_spot else target_wp.get("x", 122)
            if px < (anchor_x - 3):
                print(f"[Turret Recovery] Fell off bench to left (px={px} vs bench={anchor_x})! Walking right and jumping back onto bench...", flush=True)
                self.driver.walk("right", duration=0.12)
                self.driver.tap_key(self.jump_key)
                time.sleep(0.40)
                return "TURRET_BENCH_RECOVER_RIGHT"
            elif px > (anchor_x + 5):
                print(f"[Turret Recovery] Fell off bench to right (px={px} vs bench={anchor_x})! Walking left and jumping back onto bench...", flush=True)
                self.driver.walk("left", duration=0.12)
                self.driver.tap_key(self.jump_key)
                time.sleep(0.40)
                return "TURRET_BENCH_RECOVER_LEFT"

            # 2.2 CONTINUOUS ASYNC VISION: Read latest mob scan from background thread (0ms)
            if self.mob_watcher:
                mob_scan = self.mob_watcher.get_latest_scan()
                scan_frame = self.mob_watcher.get_latest_frame()
                if scan_frame is None and frame is not None:
                    scan_frame = frame
            else:
                scan_frame = frame if frame is not None else self.capture_frame()
                if scan_frame is None:
                    return "TURRET_NO_FRAME"
                mob_scan = self.mob_detector.scan_platform_mobs(
                    scan_frame,
                    player_center=self.player_screen_center,
                    reach_left=self.reach_left,
                    reach_right=self.reach_right,
                )
            left_active = mob_scan["left"]["active"]
            right_active = mob_scan["right"]["active"]
            left_count = mob_scan["left"].get("count", 1 if left_active else 0)
            right_count = mob_scan["right"].get("count", 1 if right_active else 0)
            total_mobs = mob_scan.get("total_count", left_count + right_count)

            # Detailed monster identification and spatial position formatting:
            mob_details = []
            rec_mobs = mob_scan.get("recognized_mobs", [])
            for m in rec_mobs:
                m_side = "LEFT" if m["dx"] < 0 else "RIGHT"
                clean_name = m["name"].replace("_clean", "")
                base = clean_name.rsplit("_", 1)[0] if "_" in clean_name else clean_name
                m_title = base.replace("_", " ").title()
                mob_details.append(f"{m_title} ({m_side} {abs(m['dx'])}px)")

            for b in mob_scan.get("left", {}).get("bars", []):
                if not any(abs(m["dx"] - b["dx"]) < 35 for m in rec_mobs):
                    mob_details.append(f"Injured Mob (LEFT {abs(b['dx'])}px)")
            for b in mob_scan.get("right", {}).get("bars", []):
                if not any(abs(m["dx"] - b["dx"]) < 35 for m in rec_mobs):
                    mob_details.append(f"Injured Mob (RIGHT {abs(b['dx'])}px)")

            mobs_str = ", ".join(mob_details) if mob_details else "None"

            # USER CONSTRAINT: มอนหมดแล้วต้องหยุดยิง! (Stop shooting when no monsters!)
            if not left_active and not right_active:
                print("[Turret Vision] Platform clear (no monsters)! Stopped shooting, waiting for spawn...", flush=True)
                time.sleep(0.20)
                return "TURRET_CLEAR_STOPPED"

            # Targeted orientation: Left is the primary platform (565px reach vs 300px right).
            # Absolute priority: If LEFT has monsters, ALWAYS attack LEFT!
            # Only turn right if LEFT is completely clear.
            if left_active:
                target_dir = "left"
            elif right_active:
                target_dir = "right"
            else:
                target_dir = None

            if not target_dir:
                time.sleep(0.10)
                return "TURRET_WAIT"

            # Check if target side actually has monsters or HP bars (ZERO GHOST SHOTS)
            target_side_bars = mob_scan.get(target_dir, {}).get("bars", [])
            target_side_rec = [m for m in rec_mobs if (m["dx"] < 0 if target_dir == "left" else m["dx"] > 0)]

            if not target_side_bars and not target_side_rec:
                print(f"[Turret Vision] Target {target_dir.upper()} confirmed clear. Stopped shooting.", flush=True)
                time.sleep(0.15)
                return "TURRET_CLEAR_STOPPED"

            # Only turn when changing direction towards the monster (quick 20ms tap to never take a step)
            if target_dir != self.turret_facing:
                print(f"[Turret Vision] Turning {target_dir.upper()} | Mobs: {mobs_str}", flush=True)
                self.turret_facing = target_dir
                dir_key = "ArrowRight" if target_dir == "right" else "ArrowLeft"
                self.driver.press_key(dir_key, duration=0.02)
                time.sleep(0.02)
            else:
                print(f"[Turret Vision] Facing {target_dir.upper()} | Active Mobs: {mobs_str}", flush=True)

            # USER CONSTRAINT: ถ้ามีมอนเกิด 3 ตัวหรือมากกว่าให้ใช้สกิล C 1 ครั้ง (คูลดาวน์ 30 วินาที)
            now = time.time()
            if total_mobs >= 3 and (now - self.last_skill_time) >= self.skill_cd:
                print(f"[Turret Vision] Density alert ({total_mobs} mobs)! Casting Skill C on {target_dir.upper()} | Mobs: {mobs_str}", flush=True)
                self.driver.tap_key(self.skill_key)
                self.last_skill_time = now
                time.sleep(0.25)
            elif target_side_bars:
                # Target has active green HP bar -> Engage continuous combat loop
                shot_cap = 2 if target_dir == "right" else 6
                combat_res = self.continuous_combat_loop(target_dir, initial_target=target_side_bars[0], max_shots=shot_cap)
                if combat_res.get("status") == "KILLED":
                    self.empty_shot_streak[target_dir] = 0
                    if self.mob_watcher:
                        self.mob_watcher.clear_scan()
                    if target_dir == "right" and left_active:
                        self.turret_facing = "left"
                        self.driver.press_key("ArrowLeft")
                    return f"TURRET_KILL_{target_dir.upper()}"
                elif combat_res.get("status") == "STAGNANT":
                    print(f"[Turret Vision] Shot target on {target_dir.upper()} stagnant (out of reach), yielding...", flush=True)
                    self.empty_shot_streak[target_dir] += 1
                    if target_dir == "right":
                        self.turret_facing = "left"
                        self.driver.press_key("ArrowLeft")
                    return f"TURRET_STAGNANT_{target_dir.upper()}"
                self.empty_shot_streak[target_dir] = 0
                return f"TURRET_COMBAT_{target_dir.upper()}"
            elif target_side_rec:
                # Full health monster (no HP bar yet) -> Fire 1 bow shot to trigger damage
                self.driver.tap_key(self.mobbing_key)
                time.sleep(0.15)
                shot_frame = self.capture_frame()
                bars = self.mob_detector.detect_monster_hp_bars(
                    shot_frame if shot_frame is not None else scan_frame,
                    facing=target_dir,
                    player_center=self.player_screen_center,
                    reach_left=self.reach_left,
                    reach_right=self.reach_right,
                    max_dist_y=160,
                )
                if bars:
                    shot_cap = 2 if target_dir == "right" else 6
                    combat_res = self.continuous_combat_loop(target_dir, initial_target=bars[0], max_shots=shot_cap)
                    if combat_res.get("status") == "KILLED":
                        self.empty_shot_streak[target_dir] = 0
                        if self.mob_watcher:
                            self.mob_watcher.clear_scan()
                        if target_dir == "right" and left_active:
                            self.turret_facing = "left"
                            self.driver.press_key("ArrowLeft")
                        return f"TURRET_KILL_{target_dir.upper()}"
                return f"TURRET_SHOT_{target_dir.upper()}"

        # 3. Standard Dynamic Waypoint Patrol (Fallback)
        tx, ty = target_wp["x"], target_wp["y"]
        dx = tx - px
        direction = "right" if dx > 0 else "left"

        # Probe shot in patrol direction
        dir_key = "ArrowRight" if direction == "right" else "ArrowLeft"
        self.driver.press_key(dir_key)
        time.sleep(0.04)
        self.driver.tap_key(self.mobbing_key)
        time.sleep(0.30)
        fresh_frame = self.capture_frame()

        target_bars = []
        if fresh_frame is not None:
            target_bars = self.mob_detector.detect_monster_hp_bars(
                fresh_frame,
                facing=direction,
                player_center=self.player_screen_center,
                reach_left=self.reach_left,
                reach_right=self.reach_right,
                max_dist_y=60,
            )

        if target_bars:
            combat_res = self.continuous_combat_loop(direction, initial_target=target_bars[0])
            if combat_res.get("status") == "KILLED":
                return f"ARCHER_KILL_LOOT_{direction.upper()}"
            return f"ARCHER_COMBAT_{direction.upper()}"

        if abs(dx) > 10:
            walk_time = min(0.85, max(0.25, abs(dx) * 0.02))
            self.driver.walk(direction, duration=walk_time)
            time.sleep(0.05)

        self.driver.tap_key(self.loot_key)
        return f"ARCHER_PATROL_{direction.upper()}"

