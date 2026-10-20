from typing import List, Optional, Tuple
import cv2
import numpy as np


class RuneSolver:
    """
    Rune 4-Direction Arrow Puzzle Solver.
    Detects the 4 directional arrows displayed on screen when interacting with a Rune.
    Directions: UP, DOWN, LEFT, RIGHT -> ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"]
    """

    KEY_MAP = {
        "UP": "ArrowUp",
        "DOWN": "ArrowDown",
        "LEFT": "ArrowLeft",
        "RIGHT": "ArrowRight",
    }

    def __init__(self, cnn_model_path: Optional[str] = None):
        self.cnn_model_path = cnn_model_path
        self.model = None
        # In future, custom PyTorch / ONNX model can be loaded here

    def is_rune_prompt_open(self, frame: np.ndarray) -> bool:
        """
        Detects if the Rune arrow prompt / banner is currently visible on screen.
        Typically appears in the center-top area (y: 15%..45%, x: 25%..75%).
        """
        fh, fw, _ = frame.shape
        cy1, cy2 = int(fh * 0.15), int(fh * 0.45)
        cx1, cx2 = int(fw * 0.25), int(fw * 0.75)
        crop = frame[cy1:cy2, cx1:cx2]

        # The Rune banner has distinctive colorful glow / circular arrow backgrounds
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        # Look for purple/teal magic aura or circular bounding discs
        mask = cv2.inRange(hsv, np.array([120, 80, 100]), np.array([170, 255, 255]))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        arrow_discs = [c for c in contours if 200 <= cv2.contourArea(c) <= 15000]
        return len(arrow_discs) >= 3

    def extract_arrow_direction_heuristic(self, arrow_crop: np.ndarray) -> str:
        """
        Determines the arrow direction (UP, DOWN, LEFT, RIGHT) using directional gradients.
        """
        gray = cv2.cvtColor(arrow_crop, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Sobel gradients
        sobel_x = cv2.Sobel(thresh, cv2.CV_64F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(thresh, cv2.CV_64F, 0, 1, ksize=3)

        sum_gx = np.sum(np.abs(sobel_x))
        sum_gy = np.sum(np.abs(sobel_y))

        # Check asymmetry between quadrants
        h, w = thresh.shape
        top_half = np.sum(thresh[: h // 2, :])
        bottom_half = np.sum(thresh[h // 2 :, :])
        left_half = np.sum(thresh[:, : w // 2])
        right_half = np.sum(thresh[:, w // 2 :])

        v_diff = top_half - bottom_half
        h_diff = left_half - right_half

        if abs(h_diff) > abs(v_diff):
            return "LEFT" if h_diff > 0 else "RIGHT"
        else:
            return "UP" if v_diff > 0 else "DOWN"

    def solve_arrows(self, frame: np.ndarray) -> List[str]:
        """
        Detects 4 arrow directions from the active frame.
        Returns list of 4 key strings, e.g. ["ArrowUp", "ArrowLeft", "ArrowRight", "ArrowDown"].
        """
        fh, fw, _ = frame.shape
        cy1, cy2 = int(fh * 0.18), int(fh * 0.40)
        cx1, cx2 = int(fw * 0.30), int(fw * 0.70)
        rune_bar = frame[cy1:cy2, cx1:cx2]

        if rune_bar.size == 0:
            return []

        # Divide into 4 equal horizontal slots
        bar_w = rune_bar.shape[1]
        slot_w = bar_w // 4
        arrow_keys = []

        for i in range(4):
            sx1 = i * slot_w
            sx2 = (i + 1) * slot_w
            slot_crop = rune_bar[:, sx1:sx2]
            direction = self.extract_arrow_direction_heuristic(slot_crop)
            key = self.KEY_MAP.get(direction, "ArrowUp")
            arrow_keys.append(key)

        return arrow_keys
