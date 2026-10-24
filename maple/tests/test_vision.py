import unittest
import numpy as np
import cv2

from maple.app.vision.minimap_tracker import MinimapTracker
from maple.app.vision.status_ocr import StatusOCR
from maple.app.vision.rune_solver import RuneSolver
from maple.app.vision.mob_detector import MobDetector
from maple.app.vision.class_gauge_reader import ClassGaugeReader


class TestVisionComponents(unittest.TestCase):

    def test_minimap_tracker_detection(self):
        tracker = MinimapTracker()
        frame = np.zeros((768, 1366, 3), dtype=np.uint8)

        # Draw a yellow dot (BGR: [0, 255, 255]) for player
        cv2.circle(frame, (80, 100), 3, (0, 255, 255), -1)
        # Draw a red dot (BGR: [0, 0, 255]) for other player
        cv2.circle(frame, (140, 100), 3, (0, 0, 255), -1)
        # Draw a purple dot (BGR: [180, 0, 180]) for rune
        cv2.circle(frame, (110, 80), 3, (180, 0, 180), -1)

        state = tracker.track(frame)
        self.assertIsNotNone(state["player_pos"])
        self.assertGreaterEqual(state["other_players_count"], 1)
        self.assertIsNotNone(state["rune_pos"])

    def test_status_ocr_gauges(self):
        status_ocr = StatusOCR()
        frame = np.zeros((768, 1366, 3), dtype=np.uint8)

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
        self.assertIsInstance(status["hp_ratio"], float)

    def test_rune_solver(self):
        solver = RuneSolver()
        frame = np.zeros((768, 1366, 3), dtype=np.uint8)
        arrows = solver.solve_arrows(frame)
        self.assertEqual(len(arrows), 4)
        for arrow in arrows:
            self.assertIn(arrow, ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"])

    def test_mob_detector(self):
        detector = MobDetector()
        frame = np.zeros((768, 1366, 3), dtype=np.uint8)
        # Draw white HP bar above a mob (BGR: 255, 255, 255)
        cv2.rectangle(frame, (400, 300), (450, 305), (255, 255, 255), -1)
        res = detector.detect_mobs(frame)
        self.assertIn("clusters", res)
        self.assertIn("elite_present", res)

    def test_class_gauge_reader(self):
        reader = ClassGaugeReader(archetype="SUMMONER")
        frame = np.zeros((768, 1366, 3), dtype=np.uint8)
        cv2.circle(frame, (500, 400), 10, (255, 200, 0), -1)

        res = reader.read_gauges(frame, archetype="SUMMONER_LARA")
        self.assertIn("detected_veins", res)
        self.assertEqual(res["archetype"], "SUMMONER_LARA")


if __name__ == "__main__":
    unittest.main()
