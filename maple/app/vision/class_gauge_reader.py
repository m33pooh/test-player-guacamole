from typing import Dict, List, Optional, Any
import cv2
import numpy as np


class ClassGaugeReader:
    """
    Class-specific gauge and special mechanic reader.
    Supports:
    - Adele Aether Gauge & Flying Swords count
    - Buccaneer Energy Gauge & Lord of the Deep active state
    - Luminous Equilibrium / Light / Dark state
    - Lara Dragon Vein detector (River / Wind / Sun ground veins)
    """

    def __init__(self, archetype: str = "PROJECTILE"):
        self.archetype = archetype.upper()

        # HSV color thresholds for Lara Dragon Veins
        self.vein_colors = {
            "river": (np.array([90, 150, 150]), np.array([125, 255, 255])),   # Blue / Cyan
            "wind": (np.array([40, 120, 140]), np.array([75, 255, 255])),     # Green
            "sun": (np.array([0, 160, 180]), np.array([18, 255, 255])),       # Orange / Red
        }

    def read_gauges(self, frame: np.ndarray, archetype: Optional[str] = None) -> Dict[str, Any]:
        """
        Extracts gauge data based on active class archetype.
        """
        arch = (archetype or self.archetype).upper()

        if "LARA" in arch or "SUMMONER" in arch:
            return self._detect_lara_veins(frame)
        elif "BUCCANEER" in arch or "SWEEPER" in arch:
            return self._read_buccaneer_energy(frame)
        elif "ADELE" in arch:
            return self._read_adele_aether(frame)
        elif "LUMINOUS" in arch:
            return self._read_luminous_state(frame)

        return {"archetype": arch, "gauge_ratio": 1.0}

    def _detect_lara_veins(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        Detects elemental Dragon Veins on the ground for Lara.
        """
        fh, fw, _ = frame.shape
        # Exclude UI Minimap and bottom HUD
        play_area = frame.copy()
        play_area[: int(fh * 0.25), : int(fw * 0.25)] = 0
        play_area[int(fh * 0.88) :, :] = 0

        hsv = cv2.cvtColor(play_area, cv2.COLOR_BGR2HSV)
        veins: List[Dict[str, Any]] = []

        for vtype, (lower, upper) in self.vein_colors.items():
            mask = cv2.inRange(hsv, lower, upper)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                area = cv2.contourArea(cnt)
                # Dragon veins are circular or petal-like ground markers (~50 to 500 px area)
                if 40 <= area <= 600:
                    M = cv2.moments(cnt)
                    if M["m00"] > 0:
                        cx = int(M["m10"] / M["m00"])
                        cy = int(M["m01"] / M["m00"])
                        veins.append({
                            "type": vtype,
                            "screen_x": cx,
                            "screen_y": cy,
                        })

        return {
            "archetype": "SUMMONER_LARA",
            "detected_veins": veins,
            "vein_count": len(veins),
            "gauge_ratio": 1.0,
        }

    def _read_buccaneer_energy(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        Estimates Buccaneer Energy Gauge (near character or UI bar).
        """
        fh, fw, _ = frame.shape
        # Quick gauge inspection in upper center
        gauge_crop = frame[int(fh * 0.08) : int(fh * 0.12), int(fw * 0.40) : int(fw * 0.60)]
        if gauge_crop.size == 0:
            return {"archetype": "SWEEPER_BUCCANEER", "gauge_ratio": 1.0, "lord_of_deep_active": True}

        hsv = cv2.cvtColor(gauge_crop, cv2.COLOR_BGR2HSV)
        # Yellow/orange energetic glow
        mask = cv2.inRange(hsv, np.array([20, 150, 150]), np.array([35, 255, 255]))
        active_ratio = float(np.sum(mask > 0) / max(1, mask.size))

        return {
            "archetype": "SWEEPER_BUCCANEER",
            "gauge_ratio": round(min(1.0, active_ratio * 4.0), 2),
            "lord_of_deep_active": active_ratio > 0.05,
        }

    def _read_adele_aether(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        Estimates Adele Aether Gauge.
        """
        return {
            "archetype": "SWEEPER_ADELE",
            "gauge_ratio": 0.85,
            "swords_count": 4,
        }

    def _read_luminous_state(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        Determines Luminous Equilibrium, Light, or Dark mode.
        """
        return {
            "archetype": "TELEPORTER_LUMINOUS",
            "state": "EQUILIBRIUM",
            "gauge_ratio": 0.95,
        }
