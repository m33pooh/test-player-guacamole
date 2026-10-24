import os
import unittest
from maple.app.navigation.platform_graph import PlatformGraph, Platform, PlatformEdge
from maple.app.navigation.pathfinder import Pathfinder

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestNavigationComponents(unittest.TestCase):

    def test_platform_graph_creation(self):
        graph = PlatformGraph()
        p1 = Platform(id="plat_1", y=100, x_min=0, x_max=100)
        p2 = Platform(id="plat_2", y=50, x_min=50, x_max=150)
        graph.add_platform(p1)
        graph.add_platform(p2)
        graph.add_edge(PlatformEdge("plat_1", "plat_2", "ROPE_LIFT", cost=1.0))

        self.assertEqual(len(graph.platforms), 2)
        found = graph.find_platform(x=50, y=100)
        self.assertIsNotNone(found)
        self.assertEqual(found.id, "plat_1")

    def test_platform_graph_load_yaml(self):
        map_path = os.path.join(PROJECT_ROOT, "maple", "configs", "maps", "limina_1_4.yaml")
        self.assertTrue(os.path.exists(map_path), f"Map yaml missing: {map_path}")
        graph = PlatformGraph.load_from_yaml(map_path)

        self.assertIn("plat_bottom", graph.platforms)
        self.assertIn("plat_top", graph.platforms)

        pathfinder = Pathfinder(graph)
        steps = pathfinder.plan_path(start_x=50, start_y=112, target_x=80, target_y=60)
        self.assertGreater(len(steps), 0)
        actions = [s["action"] for s in steps]
        self.assertTrue(any("ROPE_LIFT" in a or "FLASH_JUMP" in a or "WALK" in a for a in actions))


if __name__ == "__main__":
    unittest.main()
