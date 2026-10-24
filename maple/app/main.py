import argparse
import os
import sys
import time
from typing import Optional
import yaml
import numpy as np
import cv2

# Ensure repository root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from maple.app.capture.guacamole_capture import GuacamoleCapture
from maple.app.capture.dxgi_capture import DXGICapture
from maple.app.controller.input_driver import GuacamoleInputDriver
from maple.app.controller.timing_jitter import GaussianTimingJitter
from maple.app.vision.minimap_tracker import MinimapTracker
from maple.app.vision.status_ocr import StatusOCR
from maple.app.vision.mob_detector import MobDetector
from maple.app.vision.async_mob_watcher import AsyncMobWatcher
from maple.app.vision.rune_solver import RuneSolver
from maple.app.vision.vlm_inspector import VLMInspector
from maple.app.navigation.platform_graph import PlatformGraph
from maple.app.navigation.pathfinder import Pathfinder
from maple.app.state_machine.rotation_farm import RotationFarmEngine
from maple.app.state_machine.rune_state import RuneSolvingEngine
from maple.app.state_machine.channel_surfer import ChannelSurfer
from maple.app.state_machine.core_fsm import MapleStateMachine, MapleState
from maple.app.agent.memory_db import MemoryDB
from maple.app.agent.strategic_planner import StrategicPlanner


from maple.app.vision.class_gauge_reader import ClassGaugeReader
from maple.app.agent.buff_synchronizer import BuffSynchronizer


class MapleStoryAgent:
    """
    MapleStory AI Farming Agent with Guacamole Web Remote integration.
    Implements a Hybrid Fast/Slow loop:
    - Fast Loop (16-33ms): Frame capture, Minimap tracking, HP status, Reactive FSM.
    - Slow Path (periodic/event): Strategic LLM optimization & VLM security checks.
    """

    def __init__(
        self,
        guacamole_url: Optional[str] = None,
        cdp_endpoint: str = "http://localhost:9222",
        map_config_path: Optional[str] = None,
        class_config_path: Optional[str] = None,
        simulate: bool = False,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.simulate = simulate
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        default_map = "henesys_hunting_ground_1.yaml" if os.path.exists(os.path.join(base_dir, "configs", "maps", "henesys_hunting_ground_1.yaml")) else "ellinia_tree_dungeon.yaml"
        map_path = map_config_path or os.path.join(base_dir, "configs", "maps", default_map)
        class_path = class_config_path or os.path.join(base_dir, "configs", "classes", "archer.yaml")

        with open(map_path, "r", encoding="utf-8") as f:
            self.map_config = yaml.safe_load(f)

        with open(class_path, "r", encoding="utf-8") as f:
            self.class_config = yaml.safe_load(f)

        archetype = self.class_config.get("archetype", "PROJECTILE")

        # 1. Capture & Controller
        self.dxgi_capture = DXGICapture()
        self.capture = GuacamoleCapture(
            guacamole_url=guacamole_url,
            cdp_endpoint=cdp_endpoint,
            username=username,
            password=password,
        )
        self.jitter = GaussianTimingJitter()
        self.driver = GuacamoleInputDriver(jitter=self.jitter)

        # 2. Vision Layer
        self.minimap_tracker = MinimapTracker()
        self.status_ocr = StatusOCR()
        self.mob_detector = MobDetector()
        self.rune_solver = RuneSolver()
        self.vlm_inspector = VLMInspector()
        self.gauge_reader = ClassGaugeReader(archetype=archetype)

        # 3. Navigation Layer
        self.platform_graph = PlatformGraph.load_from_yaml(map_path)
        self.pathfinder = Pathfinder(self.platform_graph)

        # 4. Agent & Telemetry
        self.memory_db = MemoryDB()
        self.planner = StrategicPlanner()
        self.buff_sync = BuffSynchronizer()

        # 4. Continuous Async Mob Watcher Background Thread (24/7 Mob Counting)
        island_reach = self.map_config.get("island_reach", {})
        reach_left = int(island_reach.get("left", 600))
        reach_right = int(island_reach.get("right", 375))
        player_center = tuple(self.map_config.get("player_screen_center", [1065, 700]))
        self.mob_watcher = AsyncMobWatcher(
            cdp_endpoint=cdp_endpoint,
            player_center=player_center,
            reach_left=reach_left,
            reach_right=reach_right,
            target_fps=20.0,
            mob_detector=self.mob_detector,
        )

        # 5. State Machine Sub-engines
        self.rotation_engine = RotationFarmEngine(
            driver=self.driver,
            pathfinder=self.pathfinder,
            map_config=self.map_config,
            class_config=self.class_config,
            mob_detector=self.mob_detector,
            capture_fn=self.capture.capture_frame,
            mob_watcher=self.mob_watcher,
        )
        self.rune_engine = RuneSolvingEngine(
            driver=self.driver,
            pathfinder=self.pathfinder,
            rune_solver=self.rune_solver,
            interact_key=self.class_config.get("skills", {}).get("interact", "Space"),
        )
        self.channel_surfer = ChannelSurfer(driver=self.driver, ks_threshold_sec=0.0)

        # 6. Core FSM Orchestrator
        skills = self.class_config.get("skills", {})
        potion_key = skills.get("potion", "d")
        mana_potion_key = skills.get("mana_potion", "f")
        self.fsm = MapleStateMachine(
            driver=self.driver,
            rotation_engine=self.rotation_engine,
            rune_engine=self.rune_engine,
            channel_surfer=self.channel_surfer,
            memory_db=self.memory_db,
            potion_key=potion_key,
            mana_potion_key=mana_potion_key,
            buff_sync=self.buff_sync,
        )

        self.last_slow_path_time = 0.0
        self.slow_path_interval = 300.0  # Every 5 minutes

    def start(self, duration_seconds: float = 0.0, target_fps: float = 30.0):
        print("=" * 65)
        print(" AI MapleStory Farming Agent (Guacamole Web Remote)")
        print(f" Map: {self.map_config.get('map_name', 'Unknown')}")
        print(f" Class: {self.class_config.get('class_name', 'Unknown')}")
        print(f" Mode: {'SIMULATION' if self.simulate else 'LIVE GUACAMOLE REMOTE'}")
        print("=" * 65)

        if not self.simulate:
            # 1. Connect directly to browser over CDP (no OS focus stealing, mouse remains untouched)
            connected = self.capture.connect()
            if connected and self.capture.page:
                print("[MapleAgent] Connected directly to browser via CDP! (Zero OS focus stealing, mouse is free)", flush=True)
                self.driver.set_page(self.capture.page)
            else:
                # 2. Fallback to direct window capture
                attached_window = self.dxgi_capture.connect()
                if attached_window and self.dxgi_capture.target_hwnd:
                    safe_title = self.dxgi_capture.target_title.encode('ascii', errors='replace').decode('ascii')
                    print(f"[MapleAgent] Attached to window: '{safe_title}' without resizing!", flush=True)
                    self.capture = self.dxgi_capture
                    self.driver.set_hwnd(self.dxgi_capture.target_hwnd)
                else:
                    print("[MapleAgent Error] Remote stream connection was not established.", flush=True)
            if not self.simulate:
                print("[MapleAgent] Initializing: Standing up from chair and preparing for combat...", flush=True)
                self.driver.press_key("ArrowLeft")
                time.sleep(0.06)
                self.driver.press_key("ArrowRight")
                time.sleep(0.06)

        if not self.simulate and hasattr(self, "mob_watcher") and self.mob_watcher:
            self.mob_watcher.start()

        start_time = time.time()
        frame_interval = 1.0 / max(1.0, target_fps)

        try:
            while True:
                t0 = time.time()
                if duration_seconds > 0 and (t0 - start_time) >= duration_seconds:
                    print(f"[MapleAgent] Target duration ({duration_seconds}s) reached.", flush=True)
                    break

                # 1. FAST PATH: Screen Capture
                if not self.simulate:
                    frame = self.capture.capture_frame()
                else:
                    # Synthetic test frame (1366x768)
                    frame = np.zeros((768, 1366, 3), dtype=np.uint8)

                if frame is None:
                    time.sleep(0.05)
                    continue

                # 2. FAST PATH: Vision & State Extraction
                minimap_state = self.minimap_tracker.track(frame)
                status_state = self.status_ocr.read_status(frame)
                mob_state = self.mob_detector.detect_mobs(frame)
                class_state = self.gauge_reader.read_gauges(frame)

                # Fallback to anchor_spot or safe_spot if player_pos cannot be read (e.g. minimap closed/obscured)
                if not minimap_state["player_pos"]:
                    if self.simulate:
                        wp = self.rotation_engine.get_current_waypoint()
                        minimap_state["player_pos"] = [wp["x"], wp["y"]] if wp else [64, 112]
                    else:
                        anchor = self.map_config.get("anchor_spot") or self.map_config.get("safe_spot")
                        if anchor:
                            minimap_state["player_pos"] = [anchor[0], anchor[1]]

                # 3. SLOW PATH: Periodic Strategic Planning & VLM Anomaly Check
                security_state = {"captcha_detected": False, "white_room": False}
                if (t0 - self.last_slow_path_time) >= self.slow_path_interval:
                    # 3.1 VLM Security & Anti-Bot Inspection
                    if not self.simulate:
                        vlm_res = self.vlm_inspector.inspect_scene(frame)
                        if isinstance(vlm_res, dict):
                            security_state["captcha_detected"] = bool(vlm_res.get("captcha_detected", False))
                            security_state["white_room"] = bool(vlm_res.get("white_room", False))

                    # 3.2 Performance & One-Shot Efficiency Check
                    metrics = self.memory_db.get_summary_metrics()
                    print(
                        f"\n[Slow Path] Session Metrics: Kills={metrics['session_kills']} | "
                        f"Kills/min={metrics['kills_per_minute']} | Runes={metrics['runes_solved']} ({metrics['rune_success_rate']}%)",
                        flush=True,
                    )

                    max_spawn = self.map_config.get("max_map_spawn_limit", 290.0)
                    one_shot_res = self.planner.evaluate_one_shot_efficiency(metrics["kills_per_minute"], max_spawn_cap=max_spawn)
                    print(
                        f"[Slow Path] One-Shot Status: {one_shot_res.get('status')} | "
                        f"Efficiency: {one_shot_res.get('efficiency_ratio')} | {one_shot_res.get('recommendation')}",
                        flush=True,
                    )

                    # 3.3 Dynamic Summon Optimization (Section 5.2)
                    clusters = mob_state.get("clusters", [])
                    if clusters and self.rotation_engine.loot_engine.summon_locations:
                        residual_coords = [[c["center_x"], c["center_y"]] for c in clusters]
                        cur_s = self.rotation_engine.loot_engine.summon_locations[0]
                        self.planner.optimize_summon_placement(residual_coords, cur_s)

                    # 3.4 LLM Rotation Evaluation
                    plan_res = self.planner.evaluate_rotation_efficiency(
                        metrics=metrics,
                        map_name=self.map_config.get("map_name", ""),
                        current_rotation="clockwise",
                    )
                    print(f"[Slow Path] Strategic Recommendation: {plan_res.get('recommendation')}\n", flush=True)
                    self.last_slow_path_time = t0

                # 4. FAST PATH: Reactive State Machine Tick
                step_info = self.fsm.update(
                    frame=frame,
                    minimap_state=minimap_state,
                    status_state=status_state,
                    mob_state=mob_state,
                    security_state=security_state,
                    class_state=class_state,
                )

                if (t0 - getattr(self, "last_status_log_time", 0.0)) >= 1.5:
                    p_pos = minimap_state.get("player_pos")
                    hp = status_state.get("hp_ratio", 1.0) * 100
                    mp = status_state.get("mp_ratio", 1.0) * 100
                    act = step_info.get("action", "")
                    st = step_info.get("state", "")
                    print(f"[{st}] Action: {act} | Pos: {p_pos} | HP: {hp:.0f}% | MP: {mp:.0f}%", flush=True)
                    self.last_status_log_time = t0

                # 5. Periodic 20s Capture & Telemetry Logging (User Requirement)
                if (t0 - getattr(self, "last_capture_20s_time", 0.0)) >= 20.0:
                    self.last_capture_20s_time = t0
                    cap_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "captures_10min")
                    os.makedirs(cap_dir, exist_ok=True)
                    elapsed_sec = int(t0 - start_time)
                    cap_path = os.path.join(cap_dir, f"cap_{elapsed_sec:04d}s.jpg")
                    cv2.imwrite(cap_path, frame)
                    metrics = self.memory_db.get_summary_metrics()
                    p_pos = minimap_state.get("player_pos")
                    hp = status_state.get("hp_ratio", 1.0) * 100
                    mp = status_state.get("mp_ratio", 1.0) * 100
                    print(
                        f"\n======================================================\n"
                        f"[Capture 20s] T+{elapsed_sec}s/600s | Pos: {p_pos} | HP: {hp:.0f}% | MP: {mp:.0f}% | "
                        f"Kills: {metrics['session_kills']} ({metrics['kills_per_minute']} kills/min)\n"
                        f"Saved screenshot: {cap_path}\n"
                        f"======================================================\n",
                        flush=True,
                    )

                # Maintain Target Frame Rate
                elapsed = time.time() - t0
                sleep_time = max(0.001, frame_interval - elapsed)
                time.sleep(sleep_time)

        except KeyboardInterrupt:
            print("\n[MapleAgent] Interrupted by user (Ctrl+C).", flush=True)
        finally:
            self.navigate_to_safe_spot()
            self.stop()

    def navigate_to_safe_spot(self, timeout_sec: float = 15.0):
        """
        Navigates character to a designated safe spot (e.g. far platform edge or ladder)
        and sits on chair (Home key) for safe AFK.
        """
        safe_spot = self.map_config.get("safe_spot")
        if not safe_spot:
            wps = self.map_config.get("waypoints", [])
            safe_spot = wps[0] if wps else {"x": 65, "y": 241}

        if isinstance(safe_spot, list):
            target_x, target_y = safe_spot[0], safe_spot[1]
            desc = f"({target_x}, {target_y})"
        elif isinstance(safe_spot, dict):
            target_x = safe_spot.get("x", 65)
            target_y = safe_spot.get("y", 241)
            desc = safe_spot.get("desc", f"({target_x}, {target_y})")
        else:
            target_x, target_y = 123, 80
            desc = f"({target_x}, {target_y})"
        print(f"\n[SafeSpot] Session complete. Navigating character to safe spot: {desc}...", flush=True)

        if self.simulate:
            print(f"[SafeSpot Sim] Character parked at safe spot: ({target_x}, {target_y}).", flush=True)
            return

        t_start = time.time()
        while time.time() - t_start < timeout_sec:
            frame = self.capture.capture_frame()
            if frame is None:
                time.sleep(0.1)
                continue

            mm_state = self.minimap_tracker.track(frame)
            player_pos = mm_state.get("player_pos")
            if not player_pos:
                time.sleep(0.1)
                continue

            px = player_pos[0]
            dx = target_x - px

            if abs(dx) <= 1:
                print(f"[SafeSpot] Arrived safely at destination (px={px}, target={target_x})!", flush=True)
                jump_key = self.class_config.get("skills", {}).get("jump", "Alt")
                self.driver.tap_key(jump_key)
                time.sleep(0.4)
                break

            direction = "right" if dx > 0 else "left"
            walk_dur = min(0.25, max(0.10, abs(dx) * 0.015))
            self.driver.walk(direction, duration=walk_dur)
            # Clear mobs along the path using normal attack X
            mobbing_key = self.class_config.get("skills", {}).get("mobbing", "x")
            self.driver.tap_key(mobbing_key)
            time.sleep(0.1)

        # Sit on chair for safe AFK recovery
        chair_key = self.class_config.get("skills", {}).get("chair", "Home")
        print(f"[SafeSpot] Sitting on chair ({chair_key}) for safe AFK recovery.", flush=True)
        self.driver.press_key(chair_key)
        time.sleep(0.5)

    def stop(self):
        print("\n=== Shutting down MapleStory AI Farming Agent ===", flush=True)
        if hasattr(self, "mob_watcher") and self.mob_watcher:
            self.mob_watcher.stop()
        if not self.simulate:
            self.capture.close()

        metrics = self.memory_db.get_summary_metrics()
        print("=== Session Summary ===")
        print(f" Total Duration: {metrics['session_duration_sec']} seconds")
        print(f" Total Kills: {metrics['session_kills']} ({metrics['kills_per_minute']} kills/min)")
        print(f" Runes Solved: {metrics['runes_solved']} (Success Rate: {metrics['rune_success_rate']}%)")
        print(f" Channel Hops: {metrics['channel_swaps']}")
        print("========================")


def main():
    parser = argparse.ArgumentParser(description="AI MapleStory Farming Agent (Guacamole Web Remote)")
    parser.add_argument("--guacamole-url", type=str, default=None, help="Apache Guacamole remote web URL")
    parser.add_argument("--guacamole-user", type=str, default=None, help="Apache Guacamole username")
    parser.add_argument("--guacamole-pass", type=str, default=None, help="Apache Guacamole password")
    parser.add_argument("--cdp-url", type=str, default="http://localhost:9222", help="Chrome DevTools Protocol port")
    parser.add_argument("--map", type=str, default=None, help="Path to map YAML configuration")
    parser.add_argument("--class-config", type=str, default=None, help="Path to class YAML configuration")
    parser.add_argument("--simulate", action="store_true", help="Run in simulation / dry-run mode")
    parser.add_argument("--duration", type=float, default=0.0, help="Duration to run in seconds (0 = infinite)")
    parser.add_argument("--fps", type=float, default=30.0, help="Target FPS for fast vision loop")

    args = parser.parse_args()

    agent = MapleStoryAgent(
        guacamole_url=args.guacamole_url,
        cdp_endpoint=args.cdp_url,
        map_config_path=args.map,
        class_config_path=args.class_config,
        simulate=args.simulate,
        username=args.guacamole_user,
        password=args.guacamole_pass,
    )
    agent.start(duration_seconds=args.duration, target_fps=args.fps)


if __name__ == "__main__":
    main()
