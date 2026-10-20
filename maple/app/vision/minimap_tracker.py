from typing import Dict, List, Optional, Tuple, Any
import cv2
import numpy as np


class MinimapTracker:
    """
    OpenCV-based high-speed Minimap Tracker (latency < 5ms).
    Extracts:
    - Player coordinates (Yellow dot)
    - Other player coordinates (Red dots)
    - Rune location (Purple dot)
    - Portals (Cyan/Blue markers)
    """

    def __init__(self, crop_box: Optional[Tuple[int, int, int, int]] = None):
        """
        crop_box: Optional explicit (x1, y1, x2, y2) of the minimap in frame pixels.
        If None, default relative top-left region is evaluated.
        """
        self.crop_box = crop_box

        # HSV Color Thresholds (OpenCV H: 0-179, S: 0-255, V: 0-255)
        # 1. Player (Bright Yellow dot in MapleStory)
        self.player_hsv_lower = np.array([20, 160, 180])
        self.player_hsv_upper = np.array([35, 255, 255])

        # 2. Other Players (Bright Red dots)
        self.other_hsv_lower1 = np.array([0, 160, 160])
        self.other_hsv_upper1 = np.array([10, 255, 255])
        self.other_hsv_lower2 = np.array([170, 160, 160])
        self.other_hsv_upper2 = np.array([180, 255, 255])

        # 3. Rune (Violet / Purple dot)
        self.rune_hsv_lower = np.array([130, 120, 150])
        self.rune_hsv_upper = np.array([160, 255, 255])

        # 4. Portal (Cyan / Light Blue)
        self.portal_hsv_lower = np.array([85, 140, 160])
        self.portal_hsv_upper = np.array([105, 255, 255])

        self.last_player_pos: Optional[Tuple[int, int]] = None

    def get_minimap_crop(self, frame: np.ndarray) -> Tuple[np.ndarray, int, int]:
        """
        Crops and returns (minimap_image, origin_x, origin_y).
        """
        fh, fw, _ = frame.shape
        if self.crop_box:
            x1, y1, x2, y2 = self.crop_box
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(fw, x2), min(fh, y2)
        else:
            # Typical MapleStory minimap occupies top-left corner
            x1, y1 = int(fw * 0.01), int(fh * 0.03)
            x2, y2 = int(fw * 0.28), int(fh * 0.28)

        crop = frame[y1:y2, x1:x2]
        return crop, x1, y1

    def find_player_pos(self, minimap_hsv: np.ndarray) -> Optional[Tuple[int, int]]:
        """
        Locates the player's yellow dot on the minimap.
        """
        mask = cv2.inRange(minimap_hsv, self.player_hsv_lower, self.player_hsv_upper)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best_pos = None
        best_area = 0

        for cnt in contours:
            area = cv2.contourArea(cnt)
            # Yellow dot is typically 4 to 60 pixels in area
            if 3 <= area <= 120:
                M = cv2.moments(cnt)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    if area > best_area:
                        best_area = area
                        best_pos = (cx, cy)

        if best_pos:
            self.last_player_pos = best_pos
            return best_pos
        return self.last_player_pos

    def find_other_players(self, minimap_hsv: np.ndarray) -> List[Tuple[int, int]]:
        """
        Finds all other players (Red dots) on the minimap.
        """
        mask1 = cv2.inRange(minimap_hsv, self.other_hsv_lower1, self.other_hsv_upper1)
        mask2 = cv2.inRange(minimap_hsv, self.other_hsv_lower2, self.other_hsv_upper2)
        mask = cv2.bitwise_or(mask1, mask2)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        others = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 3 <= area <= 100:
                M = cv2.moments(cnt)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    others.append((cx, cy))
        return others

    def find_rune_pos(self, minimap_hsv: np.ndarray) -> Optional[Tuple[int, int]]:
        """
        Finds Rune (Purple dot) on the minimap.
        """
        mask = cv2.inRange(minimap_hsv, self.rune_hsv_lower, self.rune_hsv_upper)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 4 <= area <= 150:
                M = cv2.moments(cnt)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    return (cx, cy)
        return None

    def find_portals(self, minimap_hsv: np.ndarray) -> List[Tuple[int, int]]:
        """
        Finds Portal markers (Cyan/Blue) on the minimap.
        """
        mask = cv2.inRange(minimap_hsv, self.portal_hsv_lower, self.portal_hsv_upper)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        portals = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 4 <= area <= 120:
                M = cv2.moments(cnt)
                if M["m00"] > 0:
                    portals.append((int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])))
        return portals

    def track(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        Full tracking pass. Returns structured minimap state.
        """
        crop, ox, oy = self.get_minimap_crop(frame)
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

        player_pos = self.find_player_pos(hsv)
        other_players = self.find_other_players(hsv)
        rune_pos = self.find_rune_pos(hsv)
        portals = self.find_portals(hsv)

        return {
            "origin": (ox, oy),
            "size": (crop.shape[1], crop.shape[0]),
            "player_pos": list(player_pos) if player_pos else None,
            "other_players": [list(p) for p in other_players],
            "other_players_count": len(other_players),
            "rune_pos": list(rune_pos) if rune_pos else None,
            "portals": [list(p) for p in portals],
        }
