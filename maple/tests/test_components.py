import os
import sys
import unittest
import numpy as np
import cv2

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from maple.app.controller.timing_jitter import GaussianTimingJitter
from maple.app.navigation.platform_graph import PlatformGraph, Platform, PlatformEdge
from maple.app.navigation.pathfinder import Pathfinder
from maple.app.vision.minimap_tracker import MinimapTracker
from maple.app.vision.status_ocr import StatusOCR
from maple.app.vision.rune_solver import RuneSolver
from maple.app.agent.memory_db import MemoryDB
from maple.app.state_machine.core_fsm import MapleState, MapleStateMachine
from maple.app.controller.input_driver import GuacamoleInputDriver
from maple.app.state_machine.rotation_farm import RotationFarmEngine
from maple.app.state_machine.rune_state import RuneSolvingEngine
from maple.app.state_machine.channel_surfer import ChannelSurfer


class TestMapleComponents(unittest.TestCase):

    def test_timing_jitter(self):
        jitter = GaussianTimingJitter()
        duration = jitter.get_press_duration()
        self.assertGreaterEqual(duration, 0.02)
        self.assertLessEqual(duration, 0.15)

    def test_platform_graph_and_pathfinder(self):
        map_path = os.path.join(PROJECT_ROOT, "maple", "configs", "maps", "limina_1_4.yaml")
        graph = PlatformGraph.load_from_yaml(map_path)
        self.assertIn("plat_bottom", graph.platforms)
        self.assertIn("plat_top", graph.platforms)

        # Platform lookup
        plat = graph.find_platform(x=50, y=112)
        self.assertIsNotNone(plat)
        self.assertEqual(plat.id, "plat_bottom")

        # Pathfinder from bottom floor to top floor
        pathfinder = Pathfinder(graph)
        steps = pathfinder.plan_path(start_x=50, start_y=112, target_x=80, target_y=60)
        self.assertGreater(len(steps), 0)
        actions = [s["action"] for s in steps]
        self.assertTrue(any("ROPE_LIFT" in a or "FLASH_JUMP" in a or "WALK" in a for a in actions))

    def test_minimap_tracker(self):
        tracker = MinimapTracker()
        # Synthetic frame (768, 1366, 3)
        frame = np.zeros((768, 1366, 3), dtype=np.uint8)

        # Draw a yellow dot (BGR: [0, 255, 255]) in minimap zone (e.g. x: 80, y: 100)
        # Note: Minimap crop is roughly x: 13..382, y: 23..215
        cv2.circle(frame, (80, 100), 3, (0, 255, 255), -1)

        # Draw a red dot (BGR: [0, 0, 255])
        cv2.circle(frame, (140, 100), 3, (0, 0, 255), -1)

        # Draw a purple dot (BGR: [180, 0, 180])
        cv2.circle(frame, (110, 80), 3, (180, 0, 180), -1)

        state = tracker.track(frame)
        self.assertIsNotNone(state["player_pos"])
        self.assertGreaterEqual(state["other_players_count"], 1)
        self.assertIsNotNone(state["rune_pos"])

    def test_status_ocr(self):
        status_ocr = StatusOCR()
        frame = np.zeros((768, 1366, 3), dtype=np.uint8)
        # Draw green/red bar at bottom
        fh, fw, _ = frame.shape
        y1, y2 = int(fh * 0.92), int(fh * 0.98)
        x1, x2 = int(fw * 0.35), int(fw * 0.50)
        # Fill half red
        mid_x = (x1 + x2) // 2
        frame[y1:y2, x1:mid_x] = (0, 0, 255)

        status = status_ocr.read_status(frame)
        self.assertIn("hp_ratio", status)
        self.assertIn("mp_ratio", status)
        self.assertIn("is_dead", status)

    def test_rune_solver(self):
        solver = RuneSolver()
        frame = np.zeros((768, 1366, 3), dtype=np.uint8)
        # Should return list of 4 keys
        arrows = solver.solve_arrows(frame)
        self.assertEqual(len(arrows), 4)
        for arrow in arrows:
            self.assertIn(arrow, ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"])

    def test_memory_db(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_db = tmp.name

        try:
            db = MemoryDB(db_path=tmp_db)
            db.record_telemetry(
                state="ROTATION_FARM",
                action="MOB_ATTACK",
                minimap_pos=[64, 112],
                hp_ratio=0.95,
                mp_ratio=0.85,
            )
            db.record_kill(10)
            db.record_rune_event(duration=3.2, success=True, arrows=["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"])
            summary = db.get_summary_metrics()
            self.assertEqual(summary["session_kills"], 10)
            self.assertEqual(summary["runes_solved"], 1)
            self.assertEqual(summary["rune_success_rate"], 100.0)
        finally:
            if os.path.exists(tmp_db):
                os.remove(tmp_db)

    def test_state_machine_flow(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_db = tmp.name

        try:
            map_path = os.path.join(PROJECT_ROOT, "maple", "configs", "maps", "limina_1_4.yaml")
            graph = PlatformGraph.load_from_yaml(map_path)
            pathfinder = Pathfinder(graph)
            driver = GuacamoleInputDriver()
            db = MemoryDB(db_path=tmp_db)

            rot_engine = RotationFarmEngine(
                driver=driver,
                pathfinder=pathfinder,
                map_config={"waypoints": [{"x": 25, "y": 112}], "summon_position": [64, 112]},
                class_config={"skills": {"jump": "Alt", "mobbing": "q", "summon": "w"}},
            )
            rune_engine = RuneSolvingEngine(driver=driver, pathfinder=pathfinder)
            channel_surfer = ChannelSurfer(driver=driver)

            fsm = MapleStateMachine(
                driver=driver,
                rotation_engine=rot_engine,
                rune_engine=rune_engine,
                channel_surfer=channel_surfer,
                memory_db=db,
            )

            frame = np.zeros((768, 1366, 3), dtype=np.uint8)
            minimap_state = {"player_pos": [25, 112], "rune_pos": None, "other_players_count": 0}
            status_state = {"hp_ratio": 1.0, "mp_ratio": 1.0, "is_dead": False}
            mob_state = {"clusters": [], "elite_present": False}
            security_state = {"captcha_detected": False, "white_room": False}

            # Normal tick
            res = fsm.update(frame, minimap_state, status_state, mob_state, security_state)
            self.assertEqual(fsm.current_state, MapleState.ROTATION_FARM)

            # Trigger emergency heal
            status_low_hp = {"hp_ratio": 0.20, "mp_ratio": 1.0, "is_dead": False}
            fsm.update(frame, minimap_state, status_low_hp, mob_state, security_state)

            # Trigger Rune transition
            minimap_with_rune = {"player_pos": [25, 112], "rune_pos": [60, 112], "other_players_count": 0}
            fsm.update(frame, minimap_with_rune, status_state, mob_state, security_state)
            self.assertEqual(fsm.current_state, MapleState.RUNE_SOLVING)

        finally:
            if os.path.exists(tmp_db):
                os.remove(tmp_db)

    def test_v2_class_gauge_reader(self):
        from maple.app.vision.class_gauge_reader import ClassGaugeReader
        reader = ClassGaugeReader(archetype="SUMMONER")
        frame = np.zeros((768, 1366, 3), dtype=np.uint8)
        # Draw a cyan/blue circle for river vein
        cv2.circle(frame, (500, 400), 10, (255, 200, 0), -1)

        res = reader.read_gauges(frame, archetype="SUMMONER_LARA")
        self.assertIn("detected_veins", res)
        self.assertIn("archetype", res)

    def test_v2_loot_cycle_engine(self):
        from maple.app.state_machine.loot_cycle import LootCycleEngine
        driver = GuacamoleInputDriver()
        graph = PlatformGraph()
        pathfinder = Pathfinder(graph)
        loot_engine = LootCycleEngine(
            driver=driver,
            pathfinder=pathfinder,
            map_config={"summon_positions": {"erda": [30, 95]}},
            total_cycle_count=15,
            loot_cycles_start=14,
        )

        self.assertFalse(loot_engine.is_looting)
        # Simulate 13 completed waypoint loops
        for _ in range(13):
            loot_engine.on_waypoint_loop_completed()
        self.assertTrue(loot_engine.is_looting)

    def test_v2_buff_synchronizer(self):
        from maple.app.agent.buff_synchronizer import BuffSynchronizer
        sync = BuffSynchronizer(fma_cooldown_sec=10.0)
        # Immediately after FMA cast (9s remaining until ready, threshold is 12s)
        sync.record_fma_used()
        self.assertTrue(sync.should_delay_rune_for_fma(tolerance_sec=12.0))

    def test_v2_strategic_planner_one_shot(self):
        from maple.app.agent.strategic_planner import StrategicPlanner
        planner = StrategicPlanner()
        # High efficiency
        res_high = planner.evaluate_one_shot_efficiency(current_kpm=280.0, max_spawn_cap=290.0)
        self.assertEqual(res_high["status"], "OPTIMAL_ONE_SHOT")

        # Low efficiency
        res_low = planner.evaluate_one_shot_efficiency(current_kpm=150.0, max_spawn_cap=290.0)
        self.assertEqual(res_low["status"], "DAMAGE_DEFICIT")

        # Summon optimization
        shifted = planner.optimize_summon_placement([[100, 50], [120, 70]], [60, 112])
        self.assertEqual(shifted, [110, 60])

    def test_v2_yaml_configs(self):
        import yaml
        configs = [
            os.path.join(PROJECT_ROOT, "maple", "configs", "classes", "bishop.yaml"),
            os.path.join(PROJECT_ROOT, "maple", "configs", "classes", "lara.yaml"),
            os.path.join(PROJECT_ROOT, "maple", "configs", "classes", "buccaneer.yaml"),
            os.path.join(PROJECT_ROOT, "maple", "configs", "maps", "carcion_beach_3.yaml"),
        ]
        for c in configs:
            self.assertTrue(os.path.exists(c), f"Missing config: {c}")
            with open(c, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                self.assertIsNotNone(data)


if __name__ == "__main__":
    unittest.main()

