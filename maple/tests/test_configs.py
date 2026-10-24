import os
import unittest
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestYamlConfigs(unittest.TestCase):

    def test_class_configs(self):
        classes_dir = os.path.join(PROJECT_ROOT, "maple", "configs", "classes")
        self.assertTrue(os.path.isdir(classes_dir), f"Directory missing: {classes_dir}")

        files = [f for f in os.listdir(classes_dir) if f.endswith(".yaml") or f.endswith(".yml")]
        self.assertGreater(len(files), 0, "No class configs found!")

        for filename in files:
            path = os.path.join(classes_dir, filename)
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            self.assertIsInstance(data, dict, f"Invalid YAML dict in {filename}")
            self.assertIn("class_name", data, f"Missing 'class_name' in {filename}")
            self.assertIn("skills", data, f"Missing 'skills' in {filename}")

    def test_map_configs(self):
        maps_dir = os.path.join(PROJECT_ROOT, "maple", "configs", "maps")
        self.assertTrue(os.path.isdir(maps_dir), f"Directory missing: {maps_dir}")

        files = [f for f in os.listdir(maps_dir) if f.endswith(".yaml") or f.endswith(".yml")]
        self.assertGreater(len(files), 0, "No map configs found!")

        for filename in files:
            path = os.path.join(maps_dir, filename)
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            self.assertIsInstance(data, dict, f"Invalid YAML dict in {filename}")
            self.assertIn("map_name", data, f"Missing 'map_name' in {filename}")
            self.assertIn("platforms", data, f"Missing 'platforms' in {filename}")


if __name__ == "__main__":
    unittest.main()
