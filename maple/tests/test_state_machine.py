import os
import unittest
import tempfile
import numpy as np

from maple.app.controller.input_driver import GuacamoleInputDriver
from maple.app.navigation.platform_graph import PlatformGraph
from maple.app.navigation.pathfinder import Pathfinder
from maple.app.agent.memory_db import MemoryDB
from maple.app.agent.buff_synchronizer import BuffSynchronizer
from maple.app.agent.strategic_planner import StrategicPlanner
from maple.app.state_machine.core_fsm import MapleState, MapleStateMachine
from maple.app.state_machine.rotation_farm import RotationFarmEngine
from maple.app.state_machine.rune_state import RuneSolvingEngine
from maple.app.state_machine.channel_surfer import ChannelSurfer
from maple.app.state_machine.loot_cycle import LootCycleEngine


class TestStateMachine(unittest.TestCase):

    def setUp(self):
        self.tmp_fd, self.tmp_db = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)

    def tearDown(self):
        if os.path.exists(self.tmp_db):
            os.remove(self.tmp_db)

    def test_memory_db_tracking(self):
        db = MemoryDB(db_path=self.tmp_db)
        db.record_telemetry(
            state="ROTATION_FARM",
            action="MOB_ATTACK",
            minimap_pos=[64, 112],
            hp_ratio=0.90,
            mp_ratio=0.80,
        )
        db.record_kill(15)
        db.record_rune_event(duration=2.5, success=True, arrows=["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"])

        summary = db.get_summary_metrics()
        self.assertEqual(summary["session_kills"], 15)
        self.assertEqual(summary["runes_solved"], 1)
        self.assertEqual(summary["rune_success_rate"], 100.0)

    def test_buff_synchronizer(self):
        sync = BuffSynchronizer(fma_cooldown_sec=10.0)
        sync.record_fma_used()
        self.assertTrue(sync.should_delay_rune_for_fma(tolerance_sec=12.0))

    def test_strategic_planner(self):
        planner = StrategicPlanner()
        res_opt = planner.evaluate_one_shot_efficiency(current_kpm=285.0, max_spawn_cap=290.0)
        self.assertEqual(res_opt["status"], "OPTIMAL_ONE_SHOT")

        res_def = planner.evaluate_one_shot_efficiency(current_kpm=120.0, max_spawn_cap=290.0)
        self.assertEqual(res_def["status"], "DAMAGE_DEFICIT")

        shift = planner.optimize_summon_placement([[100, 50], [120, 70]], [60, 112])
        self.assertEqual(shift, [110, 60])

    def test_loot_cycle_engine(self):
        driver = GuacamoleInputDriver()
        graph = PlatformGraph()
        pathfinder = Pathfinder(graph)
        loot_engine = LootCycleEngine(
            driver=driver,
            pathfinder=pathfinder,
            map_config={"summon_positions": {"erda": [30, 95]}},
            total_cycle_count=10,
            loot_cycles_start=9,
        )
        self.assertFalse(loot_engine.is_looting)
        for _ in range(8):
            loot_engine.on_waypoint_loop_completed()
        self.assertTrue(loot_engine.is_looting)

    def test_fsm_transitions(self):
        driver = GuacamoleInputDriver()
        graph = PlatformGraph()
        pathfinder = Pathfinder(graph)
        db = MemoryDB(db_path=self.tmp_db)

        rot_engine = RotationFarmEngine(
            driver=driver,
            pathfinder=pathfinder,
            map_config={"waypoints": [{"x": 25, "y": 112}], "summon_position": [64, 112]},
            class_config={"skills": {"jump": "Alt", "mobbing": "ctrl", "potion": "PageDown"}},
        )
        rune_engine = RuneSolvingEngine(driver=driver, pathfinder=pathfinder)
        channel_surfer = ChannelSurfer(driver=driver)

        fsm = MapleStateMachine(
            driver=driver,
            rotation_engine=rot_engine,
            rune_engine=rune_engine,
            channel_surfer=channel_surfer,
            memory_db=db,
            potion_key="PageDown",
        )

        frame = np.zeros((768, 1366, 3), dtype=np.uint8)
        minimap_state = {"player_pos": [25, 112], "rune_pos": None, "other_players_count": 0}
        status_state = {"hp_ratio": 1.0, "mp_ratio": 1.0, "is_dead": False}
        mob_state = {"clusters": [], "elite_present": False}
        security_state = {"captcha_detected": False, "white_room": False}

        # Tick 1: ROTATION_FARM
        fsm.update(frame, minimap_state, status_state, mob_state, security_state)
        self.assertEqual(fsm.current_state, MapleState.ROTATION_FARM)

        # Tick 2: Low HP -> Emergency Heal
        low_hp = {"hp_ratio": 0.15, "mp_ratio": 1.0, "is_dead": False}
        fsm.update(frame, minimap_state, low_hp, mob_state, security_state)

        # Tick 3: Rune detected -> RUNE_SOLVING
        minimap_with_rune = {"player_pos": [25, 112], "rune_pos": [60, 112], "other_players_count": 0}
        fsm.update(frame, minimap_with_rune, status_state, mob_state, security_state)
        self.assertEqual(fsm.current_state, MapleState.RUNE_SOLVING)


if __name__ == "__main__":
    unittest.main()
