import unittest
import time
from target_tracker import TargetMemoryTracker

class TestTargetMemoryTracker(unittest.TestCase):
    def setUp(self):
        self.tracker = TargetMemoryTracker(lock_timeout=1.0, cluster_radius=120)

    def test_single_nearest_target(self):
        player_pos = (960, 480)
        enemies = [(500, 480), (900, 480), (200, 200)]
        target = self.tracker.select_best_target(enemies, player_pos, prefer_cluster=False)
        self.assertIsNotNone(target)
        self.assertEqual((target["x"], target["y"]), (900, 480))
        self.assertEqual(target["type"], "single")

    def test_cluster_centroid_calculation(self):
        player_pos = (960, 480)
        # Cluster of 3 mobs near (300, 300)
        enemies = [(300, 300), (320, 310), (310, 290), (1200, 700)]
        target = self.tracker.select_best_target(enemies, player_pos, prefer_cluster=True)
        self.assertIsNotNone(target)
        self.assertEqual(target["type"], "cluster")
        self.assertEqual(target["mob_count"], 3)
        # Centroid should be approx (310, 300)
        self.assertAlmostEqual(target["x"], 310, delta=5)
        self.assertAlmostEqual(target["y"], 300, delta=5)

    def test_coordinate_clamping(self):
        enemies = [(50, 50), (1800, 950)]
        target = self.tracker.select_best_target(enemies, (960, 480))
        self.assertIsNotNone(target)
        self.assertGreaterEqual(target["x"], 100)
        self.assertLessEqual(target["x"], 1500)
        self.assertGreaterEqual(target["y"], 150)
        self.assertLessEqual(target["y"], 800)

    def test_target_persistence_and_update(self):
        enemies_frame1 = [(400, 400), (800, 800)]
        target = self.tracker.update_or_acquire_target(enemies_frame1)
        self.assertIsNotNone(target)
        self.assertEqual((target["x"], target["y"]), (800, 800)) # Closer to 960, 480

        # Frame 2: mob slightly moved
        enemies_frame2 = [(820, 810)]
        updated_target = self.tracker.update_or_acquire_target(enemies_frame2)
        self.assertIsNotNone(updated_target)
        # Check smoothed coordinates
        self.assertGreater(updated_target["x"], 800)
        self.assertLess(updated_target["x"], 820)

    def test_clear_target(self):
        self.tracker.update_or_acquire_target([(500, 500)])
        self.assertIsNotNone(self.tracker.get_aim_coordinates())
        self.tracker.clear_target()
        self.assertIsNone(self.tracker.get_aim_coordinates())

if __name__ == "__main__":
    unittest.main()
