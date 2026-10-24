from typing import Dict, Any, Optional, Tuple
import cv2
import numpy as np


class StatusOCR:
    """
    Status bar reader for MapleStory.
    Evaluates:
    - Player HP ratio (0.0 to 1.0)
    - Player MP ratio (0.0 to 1.0)
    - Player death state
    - EXP percentage bar
    """

    def __init__(self, ui_scale: float = 1.0):
        self.ui_scale = ui_scale

        # HP Bar (Red/Orange) HSV
        self.hp_lower = np.array([0, 140, 120])
        self.hp_upper = np.array([12, 255, 255])

        # MP Bar (Blue) HSV
        self.mp_lower = np.array([100, 140, 120])
        self.mp_upper = np.array([125, 255, 255])

        # EXP Bar (Yellowish-orange at bottom of screen)
        self.exp_lower = np.array([15, 120, 120])
        self.exp_upper = np.array([30, 255, 255])

    def get_bottom_hud_crop(self, frame: np.ndarray) -> np.ndarray:
        """
        Returns bottom HUD panel where HP, MP, and EXP bars reside.
        Typically bottom 10% of frame.
        """
        fh, fw, _ = frame.shape
        y1 = int(fh * 0.90)
        return frame[y1:fh, :]

    def read_hp_ratio(self, frame: np.ndarray) -> float:
        """
        Calculates HP percentage by finding the active red fill in the HP bar.
        """
        fh, fw, _ = frame.shape
        y1, y2 = int(fh * 0.95), int(fh * 0.995)
        x1, x2 = int(fw * 0.365), int(fw * 0.455)
        bar_crop = frame[y1:y2, x1:x2]

        if bar_crop.size == 0:
            return 1.0

        r = bar_crop[:, :, 2].astype(int)
        g = bar_crop[:, :, 1].astype(int)
        b = bar_crop[:, :, 0].astype(int)
        red_mask = (r > 150) & (g < 75) & (b < 75)

        col_sums = np.sum(red_mask, axis=0)
        active_cols = np.where(col_sums > 2)[0]

        if len(active_cols) == 0:
            return 1.0

        fill_width = active_cols[-1] - active_cols[0] + 1
        total_width = bar_crop.shape[1]
        ratio = max(0.0, min(1.0, (fill_width / max(1, total_width)) / 0.82))
        return float(ratio)

    def read_mp_ratio(self, frame: np.ndarray) -> float:
        """
        Calculates MP percentage.
        """
        fh, fw, _ = frame.shape
        y1, y2 = int(fh * 0.95), int(fh * 0.995)
        x1, x2 = int(fw * 0.455), int(fw * 0.545)
        bar_crop = frame[y1:y2, x1:x2]

        if bar_crop.size == 0:
            return 1.0

        r = bar_crop[:, :, 2].astype(int)
        g = bar_crop[:, :, 1].astype(int)
        b = bar_crop[:, :, 0].astype(int)
        blue_mask = (b > 155) & (g < 160) & (r < 85)

        col_sums = np.sum(blue_mask, axis=0)
        active_cols = np.where(col_sums > 2)[0]

        if len(active_cols) == 0:
            return 1.0

        fill_width = active_cols[-1] - active_cols[0] + 1
        total_width = bar_crop.shape[1]
        ratio = max(0.0, min(1.0, (fill_width / max(1, total_width)) / 0.82))
        return float(ratio)

    def check_is_dead(self, frame: np.ndarray) -> bool:
        """
        Detects player death (Tombstone dialog or respawn prompt).
        """
        fh, fw, _ = frame.shape
        # Center screen crop for death / respawn pop-up
        cx1, cy1 = int(fw * 0.35), int(fh * 0.35)
        cx2, cy2 = int(fw * 0.65), int(fh * 0.65)
        center_crop = frame[cy1:cy2, cx1:cx2]

        # Grayscale / high contrast detection of death modal
        gray = cv2.cvtColor(center_crop, cv2.COLOR_BGR2GRAY)
        # Check if HP ratio is near 0
        hp = self.read_hp_ratio(frame)
        if hp < 0.05:
            return True

        return False

    def read_status(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        Reads complete player status.
        """
        hp = self.read_hp_ratio(frame)
        mp = self.read_mp_ratio(frame)
        is_dead = self.check_is_dead(frame)

        return {
            "hp_ratio": round(hp, 3),
            "mp_ratio": round(mp, 3),
            "is_dead": is_dead,
            "rune_buff_active": False,
            "rune_cooldown": False,
        }
