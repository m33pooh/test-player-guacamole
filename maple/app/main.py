import argparse
import os
import sys
import time
from typing import Optional
import yaml
import numpy as np

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
    ):
        self.simulate = simulate
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # Load configs
        map_path = map_config_path or os.path.join(base_dir, "configs", "maps", "limina_1_4.yaml")
        class_path = class_config_path or os.path.join(base_dir, "configs", "classes", "night_lord.yaml")

        with open(map_path, "r", encoding="utf-8") as f:
            self.map_config = yaml.safe_load(f)

        with open(class_path, "r", encoding="utf-8") as f:
            self.class_config = yaml.safe_load(f)

        archetype = self.class_config.get("archetype", "PROJECTILE")

        # 1. Capture & Controller
        self.capture = GuacamoleCapture(guacamole_url=guacamole_url, cdp_endpoint=cdp_endpoint)
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

        # 5. State Machine Sub-engines
        self.rotation_engine = RotationFarmEngine(
            driver=self.driver,
            pathfinder=self.pathfinder,
            map_config=self.map_config,
            class_config=self.class_config,
        )
        self.rune_engine = RuneSolvingEngine(
            driver=self.driver,
            pathfinder=self.pathfinder,
            rune_solver=self.rune_solver,
            interact_key=self.class_config.get("skills", {}).get("interact", "Space"),
        )
        self.channel_surfer = ChannelSurfer(driver=self.driver)

        # 6. Core FSM Orchestrator
        potion_key = self.class_config.get("skills", {}).get("potion", "PageDown")
        self.fsm = MapleStateMachine(
            driver=self.driver,
            rotation_engine=self.rotation_engine,
            rune_engine=self.rune_engine,
            channel_surfer=self.channel_surfer,
            memory_db=self.memory_db,
            potion_key=potion_key,
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
            connected = self.capture.connect()
            if not connected:
                print("[MapleAgent Warning] Guacamole connection failed. Switching to Simulation mode.", flush=True)
                self.simulate = True
            else:
                self.driver.set_page(self.capture.page)

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

                # Simulated mock coordinates if running in simulation
                if self.simulate and not minimap_state["player_pos"]:
                    wp = self.rotation_engine.get_current_waypoint()
                    minimap_state["player_pos"] = [wp["x"], wp["y"]] if wp else [64, 112]

                security_state = {"captcha_detected": False, "white_room": False}

                # 3. SLOW PATH: Periodic Strategic Planning & VLM Anomaly Check
                if (t0 - self.last_slow_path_time) >= self.slow_path_interval:
                    metrics = self.memory_db.get_summary_metrics()
                    print(f"\n[Slow Path] Session Metrics: Kills={metrics['session_kills']} | Kills/min={metrics['kills_per_minute']} | Runes={metrics['runes_solved']} ({metrics['rune_success_rate']}%)", flush=True)

                    # 5.1 One-Shot Efficiency Check
                    max_spawn = self.map_config.get("max_map_spawn_limit", 290.0)
                    one_shot_res = self.planner.evaluate_one_shot_efficiency(metrics['kills_per_minute'], max_spawn_cap=max_spawn)
                    print(f"[Slow Path] One-Shot Status: {one_shot_res.get('status')} | Efficiency: {one_shot_res.get('efficiency_ratio')} | {one_shot_res.get('recommendation')}", flush=True)

                    # Rotation Recommendation
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

                # Maintain Target Frame Rate
                elapsed = time.time() - t0
                sleep_time = max(0.001, frame_interval - elapsed)
                time.sleep(sleep_time)

        except KeyboardInterrupt:
            print("\n[MapleAgent] Interrupted by user (Ctrl+C).", flush=True)
        finally:
            self.stop()

    def stop(self):
        print("\n=== Shutting down MapleStory AI Farming Agent ===", flush=True)
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
    )
    agent.start(duration_seconds=args.duration, target_fps=args.fps)


if __name__ == "__main__":
    main()
