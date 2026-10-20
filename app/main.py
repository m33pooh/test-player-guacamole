import argparse
import os
import sys
import time
from typing import Optional

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.agent.memory import MemoryEngine
from app.agent.planner import create_planner
from app.agent.policy import AgentPolicyEngine
from app.controller.controller import ActionController
from app.metrics.performance import PerformanceAnalyzer
from app.metrics.tracker import MetricsTracker
from app.state_machine.fsm import BotStateMachine
from app.vision.detector import FastVisionDetector
from app.vision.vlm import QwenVLStrategicBrain
from config.settings import AgentConfig, get_default_config


class FarmingAgent:
    """
    Dual-Loop AI MMORPG Farming Agent Architecture.
    - Fast Loop (30-60 Hz): Screen capture, Fast Vision (YOLO/HSV), Combat FSM & Navigation.
    - Slow Loop (every 10-15s): Strategic LLM Reasoning, VLM Scene Classification, Performance Analytics.
    """
    def __init__(self, config: Optional[AgentConfig] = None, mode: str = "auto"):
        self.config = config or get_default_config()
        self.mode = mode
        self.running = False

        # 1. Vision Layer
        self.detector = FastVisionDetector(self.config.vision)
        self.vlm = QwenVLStrategicBrain(self.config.vlm)

        # 2. Agent & Strategic Layer
        self.memory = MemoryEngine()
        self.planner = create_planner(self.config.llm)
        self.policy = AgentPolicyEngine(self.memory, self.planner)

        # 3. Action Controller
        self.controller = ActionController(self.config.controller)

        # 4. Metrics & Performance
        self.tracker = MetricsTracker()
        self.analyzer = PerformanceAnalyzer(self.tracker)

        # 5. State Machine Orchestrator
        self.fsm = BotStateMachine(
            controller=self.controller,
            policy=self.policy,
            detector=self.detector,
            vlm=self.vlm,
            config=self.config,
        )

        self.last_slow_loop_time = 0.0

    def start(self, duration_seconds: float = 0.0, target_fps: float = 30.0):
        print("=" * 60)
        print(" MMORPG AI Farming Agent - Initializing")
        print(f" Mode: {self.mode} | Controller Backend: {self.controller.backend_type}")
        print(f" VLM Backend: {self.vlm.active_backend} | LLM Planner: {type(self.planner).__name__}")
        print("=" * 60)

        # Connect controller
        self.controller.connect(mode=self.mode)
        self.running = True
        start_time = time.time()
        loop_interval = 1.0 / max(1.0, target_fps)

        # -----------------------------------------------------------------
        # STEP 0: Perform Initial LLM Check (Location, Strategy, Town Coords)
        # -----------------------------------------------------------------
        init_frame = self.controller.capture_frame()
        if init_frame is None:
            init_frame = self.detector.capture_screenshot()
        if init_frame is not None and init_frame.size > 0:
            self.fsm.perform_initial_llm_check(init_frame)

        try:
            while self.running:
                loop_start = time.time()

                if duration_seconds > 0 and (loop_start - start_time) >= duration_seconds:
                    print("[Agent] Reached target runtime duration.")
                    break

                # 1. Capture screen frame
                frame = self.controller.capture_frame()
                if frame is None:
                    frame = self.detector.capture_screenshot()

                # 2. Fast Loop: Parse GameState via Fast Vision Engine
                game_state = self.detector.parse_game_state(frame)

                # 3. Fast Loop: Execute State Machine Step
                current_state = self.fsm.step(frame, game_state)

                # 4. Telemetry logging
                self.tracker.log_action(
                    state=str(current_state),
                    action="FSM_STEP",
                    result="SUCCESS",
                    hp=game_state.character_hp,
                    mp=game_state.character_mp,
                    inventory=game_state.inventory,
                    location=game_state.location,
                )

                # 5. Slow Loop: Strategic LLM Planning (Every 12-15 seconds)
                if loop_start - self.last_slow_loop_time >= self.config.llm.planning_interval_seconds:
                    metrics_summary = self.analyzer.get_summary()
                    decision = self.policy.update_strategic_plan(game_state, metrics_summary)
                    print(
                        f"[Slow Loop Strategic AI] Target Zone: {decision.target_zone} | "
                        f"Priority: {decision.action_priority} | Strategy: {decision.skill_strategy} | "
                        f"Reasoning: {decision.reasoning}",
                        flush=True,
                    )
                    self.last_slow_loop_time = loop_start

                # Frame pacing
                elapsed = time.time() - loop_start
                sleep_time = max(0.005, loop_interval - elapsed)
                time.sleep(sleep_time)

        except KeyboardInterrupt:
            print("\n[Agent] Interrupted by user (Ctrl+C).")
        except Exception as e:
            import traceback
            print(f"\n[Agent Error] {e}")
            traceback.print_exc()
        finally:
            self.stop()

    def stop(self):
        self.running = False
        self.controller.close()
        self.analyzer.print_summary_report()
        print("[Agent] System shutdown complete.")


def main():
    parser = argparse.ArgumentParser(description="AI MMORPG Farming Agent Runner")
    parser.add_argument(
        "--mode",
        choices=["auto", "playwright", "os", "dry_run"],
        default="auto",
        help="Controller execution backend",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Session duration in seconds (0 = infinite)",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=30.0,
        help="Target Fast-Loop frequency in Hz",
    )
    args = parser.parse_args()

    agent = FarmingAgent(mode=args.mode)
    agent.start(duration_seconds=args.duration, target_fps=args.fps)


if __name__ == "__main__":
    main()
