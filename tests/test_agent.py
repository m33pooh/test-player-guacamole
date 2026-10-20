import os
import sys
import unittest
import numpy as np

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.agent.memory import MemoryEngine
from app.agent.planner import BaseLLMPlanner, StubRuleBasedPlanner, StrategicDecision, create_planner
from app.agent.policy import AgentPolicyEngine
from app.controller.controller import ActionController
from app.metrics.performance import PerformanceAnalyzer
from app.metrics.tracker import MetricsTracker
from app.state_machine.fsm import BotStateMachine
from app.state_machine.states import BotState
from app.vision.detector import FastVisionDetector, TargetMemoryTracker
from app.vision.state import GameState, TargetInfo
from app.vision.vlm import QwenVLStrategicBrain
from config.settings import AgentConfig, get_default_config


class TestMMORPGFarmingAgent(unittest.TestCase):
    def setUp(self):
        self.config = get_default_config()
        self.config.controller.backend = "dry_run"

    def test_game_state_model(self):
        state = GameState(
            location="Stormreef Isle",
            character_hp=0.85,
            character_mp=0.60,
            enemy_count=3,
        )
        d = state.to_dict()
        self.assertEqual(d["location"], "Stormreef Isle")
        self.assertEqual(d["character_hp"], 0.85)
        self.assertEqual(d["enemy_count"], 3)
        self.assertFalse(d["dead"])

    def test_target_memory_tracker_clustering(self):
        tracker = TargetMemoryTracker(cluster_radius=120)
        # 3 close enemies
        enemies = [(500, 300), (520, 310), (510, 290)]
        target = tracker.select_best_target(enemies, player_pos=(500, 500), prefer_cluster=True)
        self.assertIsNotNone(target)
        self.assertEqual(target.target_type, "cluster")
        self.assertEqual(target.mob_count, 3)

        # Single enemy
        single_enemy = [(800, 400)]
        single_target = tracker.select_best_target(single_enemy, player_pos=(500, 500))
        self.assertIsNotNone(single_target)
        self.assertEqual(single_target.target_type, "single")
        self.assertEqual(single_target.x, 800)
        self.assertEqual(single_target.y, 400)

    def test_fast_vision_detector_synthetic_frame(self):
        detector = FastVisionDetector(self.config.vision)
        # Create synthetic test frame
        frame = np.zeros((932, 1707, 3), dtype=np.uint8)
        state = detector.parse_game_state(frame)
        self.assertIsInstance(state, GameState)
        self.assertEqual(state.enemy_count, 0)

    def test_vlm_fallback(self):
        vlm = QwenVLStrategicBrain(self.config.vlm, backend="fallback")
        dummy_frame = np.zeros((200, 200, 3), dtype=np.uint8)
        res = vlm.classify_game_state(dummy_frame)
        self.assertIn("state", res)

    def test_memory_engine(self):
        memory = MemoryEngine()
        best_spot = memory.get_optimal_farming_spot()
        self.assertIsNotNone(best_spot)
        self.assertIn("x", best_spot)
        self.assertIn("y", best_spot)

        policy = memory.get_skill_policy("Gunslinger_AoE")
        self.assertIsNotNone(policy)
        self.assertIn("pull_combo", policy)

    def test_strategic_planner(self):
        planner = create_planner(self.config.llm)
        self.assertIsInstance(planner, BaseLLMPlanner)

        # Normal state
        normal_state = GameState(character_hp=0.9, enemy_count=3)
        decision = planner.plan(normal_state, {}, {})
        self.assertEqual(decision.action_priority, "farm")
        self.assertEqual(decision.skill_strategy, "aoe_heavy")

        # Dead state
        dead_state = GameState(dead=True)
        dead_decision = planner.plan(dead_state, {}, {})
        self.assertEqual(dead_decision.action_priority, "heal_recover")

    def test_openrouter_planner_headers_and_fallback(self):
        from config.settings import LLMConfig
        from app.agent.planner import OpenRouterLLMPlanner

        cfg = LLMConfig(
            provider="openrouter",
            api_key="sk-or-v1-testkey123",
            model_name="qwen/qwen-2.5-72b-instruct",
            site_url="https://test.com",
            site_name="TestApp"
        )
        planner = OpenRouterLLMPlanner(cfg)
        headers = planner._build_headers()
        self.assertEqual(headers["Authorization"], "Bearer sk-or-v1-testkey123")
        self.assertEqual(headers["HTTP-Referer"], "https://test.com")
        self.assertEqual(headers["X-Title"], "TestApp")

        # In offline/test mode without live API response, it should smoothly fallback to Rule-based decision
        dummy_state = GameState(character_hp=0.95, enemy_count=4)
        decision = planner.plan(dummy_state, {}, {})
        self.assertIsInstance(decision, StrategicDecision)
        self.assertEqual(decision.action_priority, "farm")

    def test_agent_policy_engine(self):
        memory = MemoryEngine()
        planner = StubRuleBasedPlanner()
        policy = AgentPolicyEngine(memory, planner)

        combo = policy.get_combat_combo(target_type="cluster")
        self.assertTrue(len(combo) > 0)
        self.assertIn("3", combo)
        self.assertIn("1", combo)

        self.assertEqual(policy.get_potion_key(), "5")
        self.assertEqual(policy.get_buff_key(), "6")

    def test_action_controller_dry_run(self):
        controller = ActionController(self.config.controller)
        connected = controller.connect(mode="dry_run")
        self.assertTrue(connected)
        controller.click(500, 500)
        controller.press("1")
        controller.close()

    def test_state_machine_transitions(self):
        controller = ActionController(self.config.controller)
        controller.connect(mode="dry_run")
        memory = MemoryEngine()
        planner = StubRuleBasedPlanner()
        policy = AgentPolicyEngine(memory, planner)
        detector = FastVisionDetector(self.config.vision)
        vlm = QwenVLStrategicBrain(self.config.vlm, backend="fallback")

        fsm = BotStateMachine(
            controller=controller,
            policy=policy,
            detector=detector,
            vlm=vlm,
            config=self.config,
        )

        dummy_frame = np.zeros((932, 1707, 3), dtype=np.uint8)

        # Test Dead -> Full Town Recovery Cycle -> In Field
        dead_state = GameState(dead=True)
        fsm.step(dummy_frame, dead_state)
        self.assertEqual(fsm.current_state, BotState.IN_FIELD)

        # Test In Town -> Full Recovery Cycle -> In Field
        fsm.current_state = BotState.IN_TOWN
        fsm.step(dummy_frame, GameState(in_town=True))
        self.assertEqual(fsm.current_state, BotState.IN_FIELD)

        # Test In Field -> Combat Transition
        combat_state = GameState(enemy_count=2, target_pos=(500, 300))
        fsm.step(dummy_frame, combat_state)
        self.assertEqual(fsm.current_state, BotState.COMBAT)

    def test_metrics_and_performance(self):
        tracker = MetricsTracker()
        analyzer = PerformanceAnalyzer(tracker)

        analyzer.add_kill()
        analyzer.add_kill()
        analyzer.add_xp(500)
        analyzer.add_gold(100)

    def test_gunslinger_skill_rotation_and_big_monster(self):
        from app.state_machine.combat import CombatStateHandler
        controller = ActionController(self.config.controller)
        controller.connect(mode="dry_run")
        memory = MemoryEngine()
        planner = StubRuleBasedPlanner()
        policy = AgentPolicyEngine(memory, planner)
        combat_handler = CombatStateHandler(controller, policy)

        # 1. Normal AoE Combat state
        normal_state = GameState(enemy_count=5, target_pos=(600, 400), target_is_big=False)
        acted = combat_handler.execute_combat_cycle(normal_state, player_pos=(500, 500))
        self.assertTrue(acted)
        self.assertIn("3", combat_handler.last_cast)
        self.assertIn("1", combat_handler.last_cast)
        self.assertIn("y", combat_handler.last_cast)
        self.assertIn("t", combat_handler.last_cast)

        # 2. Big Monster combat state
        big_state = GameState(enemy_count=2, target_pos=(700, 450), target_is_big=True)
        acted_big = combat_handler.execute_combat_cycle(big_state, player_pos=(500, 500))
        self.assertTrue(acted_big)
        self.assertIn("e", combat_handler.last_cast)
        self.assertIn("q", combat_handler.last_cast)


if __name__ == "__main__":
    unittest.main()
