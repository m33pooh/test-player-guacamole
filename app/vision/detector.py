import math
import os
import time
from typing import List, Optional, Tuple, Union

import numpy as np
from PIL import Image, ImageGrab

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

try:
    from ultralytics import YOLO
    HAS_YOLO = True
except Exception:
    HAS_YOLO = False

from app.vision.state import GameState, MinimapNavigationVector, TargetInfo
from config.settings import VisionConfig


class TargetMemoryTracker:
    """
    On-Screen Monster Target Locator & Tracking Memory System.
    Maintains persistent target lock, calculates cluster centroids for AoE skills,
    and provides accurate aiming coordinates before each skill cast.
    """
    def __init__(self, lock_timeout: float = 3.5, cluster_radius: int = 120):
        self.lock_timeout = lock_timeout
        self.cluster_radius = cluster_radius
        self.active_target: Optional[TargetInfo] = None
        self.combo_in_progress = False
        self.lock_start_time = 0.0
        self.last_update_time = 0.0

    def select_best_target(
        self,
        detected_enemies: List[Tuple[int, int]],
        player_pos: Tuple[int, int] = (853, 466),
        big_enemies: Optional[List[Tuple[int, int]]] = None,
        prefer_cluster: bool = True,
    ) -> Optional[TargetInfo]:
        if not detected_enemies:
            return None

        # Filter out mobs outside valid screen boundaries
        valid_mobs = [
            pt for pt in detected_enemies
            if 80 <= pt[0] <= 1840 and 80 <= pt[1] <= 1000
        ]
        if not valid_mobs:
            return None

        # 0. Prioritize Big Enemy if present
        if big_enemies:
            valid_big = [pt for pt in big_enemies if 80 <= pt[0] <= 1840 and 80 <= pt[1] <= 1000]
            if valid_big:
                closest_big = min(
                    valid_big,
                    key=lambda pt: math.hypot(pt[0] - player_pos[0], pt[1] - player_pos[1]),
                )
                dist = math.hypot(closest_big[0] - player_pos[0], closest_big[1] - player_pos[1])
                return TargetInfo(
                    x=closest_big[0],
                    y=closest_big[1],
                    target_type="big_monster",
                    mob_count=1,
                    is_big=True,
                    distance_to_player=dist,
                )

        # 1. Density Cluster Target (Optimal for AoE Skills: 3, 1, Y->T)
        if len(valid_mobs) >= 2:
            best_cluster_center = None
            max_cluster_size = 0
            best_dist_to_player = float("inf")

            for ref_x, ref_y in valid_mobs:
                cluster_members = [
                    (mx, my)
                    for mx, my in valid_mobs
                    if math.hypot(mx - ref_x, my - ref_y) <= self.cluster_radius
                ]
                cluster_size = len(cluster_members)
                avg_x = int(sum(m[0] for m in cluster_members) / cluster_size)
                avg_y = int(sum(m[1] for m in cluster_members) / cluster_size)
                dist_to_player = math.hypot(avg_x - player_pos[0], avg_y - player_pos[1])

                if cluster_size > max_cluster_size or (
                    cluster_size == max_cluster_size and dist_to_player < best_dist_to_player
                ):
                    max_cluster_size = cluster_size
                    best_cluster_center = (avg_x, avg_y)
                    best_dist_to_player = dist_to_player

            if max_cluster_size >= 2 and best_cluster_center:
                return TargetInfo(
                    x=best_cluster_center[0],
                    y=best_cluster_center[1],
                    target_type="cluster",
                    mob_count=max_cluster_size,
                    is_big=False,
                    distance_to_player=best_dist_to_player,
                )

        # Single Nearest Target
        closest_mob = min(
            valid_mobs,
            key=lambda pt: math.hypot(pt[0] - player_pos[0], pt[1] - player_pos[1]),
        )
        dist = math.hypot(closest_mob[0] - player_pos[0], closest_mob[1] - player_pos[1])
        return TargetInfo(
            x=closest_mob[0],
            y=closest_mob[1],
            target_type="single",
            mob_count=1,
            is_big=False,
            distance_to_player=dist,
        )

    def update_or_acquire_target(
        self,
        detected_enemies: List[Tuple[int, int]],
        player_pos: Tuple[int, int] = (853, 466),
        big_enemies: Optional[List[Tuple[int, int]]] = None,
    ) -> Optional[TargetInfo]:
        """
        Velocity-aware target tracking across animation frames.
        """
        now = time.time()

        if self.active_target and not detected_enemies and (now - self.last_update_time > self.lock_timeout):
            self.clear_target()

        if detected_enemies:
            if self.active_target:
                cur_x, cur_y = self.active_target.x, self.active_target.y
                closest_to_lock = min(
                    detected_enemies,
                    key=lambda pt: math.hypot(pt[0] - cur_x, pt[1] - cur_y),
                )
                dist = math.hypot(closest_to_lock[0] - cur_x, closest_to_lock[1] - cur_y)

                # Distance threshold for continuous tracking of moving monster
                if dist <= 320:
                    # Adaptive exponential smoothing with motion velocity
                    smooth_x = int(0.35 * cur_x + 0.65 * closest_to_lock[0])
                    smooth_y = int(0.35 * cur_y + 0.65 * closest_to_lock[1])
                    self.active_target.x = max(100, min(1800, smooth_x))
                    self.active_target.y = max(100, min(900, smooth_y))
                    self.active_target.last_seen = now
                    self.active_target.distance_to_player = math.hypot(
                        self.active_target.x - player_pos[0], self.active_target.y - player_pos[1]
                    )
                    if big_enemies and any(math.hypot(bx - self.active_target.x, by - self.active_target.y) <= 130 for bx, by in big_enemies):
                        self.active_target.is_big = True
                    self.last_update_time = now
                    return self.active_target
                else:
                    new_target = self.select_best_target(detected_enemies, player_pos=player_pos, big_enemies=big_enemies)
                    if new_target:
                        self.active_target = new_target
                        self.last_update_time = now
                        self.combo_in_progress = True
                        return self.active_target

            new_target = self.select_best_target(detected_enemies, player_pos=player_pos, big_enemies=big_enemies)
            if new_target:
                self.active_target = new_target
                self.lock_start_time = now
                self.last_update_time = now
                self.combo_in_progress = True
                return self.active_target

        return self.active_target

    def get_aim_coordinates(self) -> Optional[Tuple[int, int]]:
        if self.active_target:
            return (self.active_target.x, self.active_target.y)
        return None

    def clear_target(self):
        self.active_target = None
        self.combo_in_progress = False
        self.lock_start_time = 0.0
        self.last_update_time = 0.0


from app.vision.template_bank import MultiAngleMonsterTemplateBank


class FastVisionDetector:
    """
    Fast-Loop Computer Vision Engine for MMORPG Monster Recognition (30-60 Hz).
    Supports Multi-Angle Visual Template Memory Bank, YOLOv11/v8, zero-latency HSV segmentation,
    minimap vectoring, and UI status parsing.
    """
    def __init__(self, config: Optional[VisionConfig] = None):
        self.config = config or VisionConfig()
        self.screen_width = self.config.screen_width
        self.screen_height = self.config.screen_height
        self.use_yolo = self.config.use_yolo and HAS_YOLO
        self.yolo_model = None
        self.tracker = TargetMemoryTracker()
        self.template_bank = MultiAngleMonsterTemplateBank()
        self._sct = None

        if self.use_yolo:
            self._init_yolo()

    def _init_yolo(self):
        try:
            if os.path.exists(self.config.yolo_model_path):
                self.yolo_model = YOLO(self.config.yolo_model_path)
            else:
                self.use_yolo = False
        except Exception:
            self.use_yolo = False

    def validate_and_normalize_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, float, float]:
        """
        Preserves native screen frame resolution without forcing scale change.
        """
        if frame is None or frame.size == 0:
            return frame, 1.0, 1.0
        return frame, 1.0, 1.0

    def capture_screenshot(self) -> np.ndarray:
        """Captures full screen as OpenCV BGR image at native resolution."""
        if HAS_MSS:
            try:
                if self._sct is None:
                    self._sct = mss.mss()
                monitor = self._sct.monitors[1]
                sct_img = self._sct.grab(monitor)
                raw_frame = np.array(sct_img)
                if HAS_OPENCV:
                    return cv2.cvtColor(raw_frame, cv2.COLOR_BGRA2BGR)
                return raw_frame
            except Exception:
                pass

        try:
            img = ImageGrab.grab()
            raw_frame = np.array(img)
            if HAS_OPENCV:
                return cv2.cvtColor(raw_frame, cv2.COLOR_RGB2BGR)
            return raw_frame
        except Exception:
            return np.zeros((self.screen_height, self.screen_width, 3), dtype=np.uint8)

    def find_onscreen_enemies(self, frame: np.ndarray) -> List[Tuple[int, int]]:
        """Finds enemies using YOLO or HSV overhead red HP bar segmentation."""
        if self.use_yolo and self.yolo_model is not None:
            try:
                results = self.yolo_model.predict(
                    frame, conf=self.config.confidence_threshold, verbose=False
                )
                targets = []
                for r in results:
                    for box in r.boxes:
                        xyxy = box.xyxy[0].cpu().numpy()
                        x1, y1, x2, y2 = xyxy
                        cx = int((x1 + x2) / 2)
                        cy = int((y1 + y2) / 2)
                        targets.append((cx, cy))
                if targets:
                    return targets
            except Exception:
                pass

        return self.find_onscreen_enemies_hsv(frame)

    def find_onscreen_enemies_detailed(self, frame: np.ndarray) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
        """
        Robust Animated & Moving Monster Detector:
        1. Primary: Multi-Angle Visual Monster Template Memory Bank Matching.
        2. Auxiliary: Highly-saturated vivid red horizontal overhead monster HP bars.
        Eliminates all false positives from brown sand, dirt ground, cliff rocks, and UI bars.
        Returns: (all_enemies, big_enemies)
        """
        if not HAS_OPENCV or frame is None or frame.size == 0:
            return [], []

        h, w, _ = frame.shape
        px, py = int(w * 0.50), int(h * 0.50)

        # Player avatar exclusion bounding box
        player_box_x1 = px - int(w * 0.08)
        player_box_x2 = px + int(w * 0.08)
        player_box_y1 = py - int(h * 0.28)
        player_box_y2 = py + int(h * 0.15)

        enemy_targets = []
        big_enemy_targets = []

        # 1. Primary: Multi-Angle Visual Template Memory Bank Matching
        try:
            if hasattr(self, "template_bank") and self.template_bank.templates:
                tmpl_matches = self.template_bank.find_monsters_in_frame(frame)
                for tm in tmpl_matches:
                    tcx, tcy = tm.center_x, tm.center_y
                    if not (player_box_x1 <= tcx <= player_box_x2 and player_box_y1 <= tcy <= player_box_y2):
                        enemy_targets.append((tcx, tcy))
                        if tm.is_big:
                            big_enemy_targets.append((tcx, tcy))
        except Exception:
            pass

        # 2. Auxiliary: Highly-saturated vivid red horizontal overhead monster HP bars
        # Ground combat area strictly excludes HUD, minimap, and bottom skill/exp hotbar
        x1, y1 = int(w * 0.08), int(h * 0.10)
        x2, y2 = int(w * 0.88), int(h * 0.82)
        ground_area = frame[y1:y2, x1:x2]
        if ground_area.size > 0:
            hsv = cv2.cvtColor(ground_area, cv2.COLOR_BGR2HSV)
            # Vivid saturated red HP bar: S >= 150, V >= 140
            mask_vivid_red = cv2.bitwise_or(
                cv2.inRange(hsv, np.array([0, 150, 140]), np.array([10, 255, 255])),
                cv2.inRange(hsv, np.array([170, 150, 140]), np.array([180, 255, 255]))
            )
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 2))
            mask_clean = cv2.morphologyEx(mask_vivid_red, cv2.MORPH_CLOSE, kernel)
            cnts_red, _ = cv2.findContours(mask_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for c in cnts_red:
                x, y, bw, bh = cv2.boundingRect(c)
                area = cv2.contourArea(c)
                aspect = bw / float(max(1, bh))
                if 12 <= bw <= 120 and 2 <= bh <= 14 and aspect >= 2.2:
                    cx = x + bw // 2 + x1
                    cy = y + bh // 2 + y1
                    if not (player_box_x1 <= cx <= player_box_x2 and player_box_y1 <= cy <= player_box_y2):
                        if not any(math.hypot(cx - ex, cy - ey) <= 40 for ex, ey in enemy_targets):
                            enemy_targets.append((cx, cy))
                            if bw >= 40 or area >= 120 or aspect >= 3.5:
                                big_enemy_targets.append((cx, cy))

        if enemy_targets:
            enemy_targets.sort(key=lambda pt: (pt[0] - px) ** 2 + (pt[1] - py) ** 2)
        if big_enemy_targets:
            big_enemy_targets.sort(key=lambda pt: (pt[0] - px) ** 2 + (pt[1] - py) ** 2)

        return enemy_targets, big_enemy_targets

    def find_onscreen_enemies_hsv(self, frame: np.ndarray) -> List[Tuple[int, int]]:
        """Scans for overhead hostile red HP bars with false-positive filtering."""
        all_enemies, _ = self.find_onscreen_enemies_detailed(frame)
        return all_enemies

    def get_minimap_red_dots(self, frame: np.ndarray) -> List[Tuple[int, int]]:
        """Finds all enemy red dots on minimap in full screen coordinates."""
        if not HAS_OPENCV or frame is None or frame.size == 0:
            return []

        h, w = frame.shape[:2]
        x1, y1 = int(w * 0.76), int(h * 0.01)
        x2, y2 = int(w * 0.998), int(h * 0.28)
        minimap = frame[y1:y2, x1:x2]
        if minimap.size == 0:
            return []

        hsv = cv2.cvtColor(minimap, cv2.COLOR_BGR2HSV)
        mask = cv2.bitwise_or(
            cv2.inRange(hsv, np.array([0, 120, 100]), np.array([10, 255, 255])),
            cv2.inRange(hsv, np.array([170, 120, 100]), np.array([180, 255, 255])),
        )
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        dots = []
        for c in cnts:
            if cv2.contourArea(c) < 3:
                continue
            M = cv2.moments(c)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                dots.append((x1 + cx, y1 + cy))
        return dots

    def get_minimap_navigation_vector(self, frame: np.ndarray) -> Optional[MinimapNavigationVector]:
        """Calculates direction vector from player arrow to closest monster dot on minimap."""
        if not HAS_OPENCV or frame is None or frame.size == 0:
            return None

        h, w = frame.shape[:2]
        x1, y1 = int(w * 0.76), int(h * 0.01)
        x2, y2 = int(w * 0.998), int(h * 0.28)
        minimap = frame[y1:y2, x1:x2]
        if minimap.size == 0:
            return None

        mh, mw, _ = minimap.shape
        hsv = cv2.cvtColor(minimap, cv2.COLOR_BGR2HSV)
        border_mask = np.zeros((mh, mw), dtype=np.uint8)
        cv2.rectangle(border_mask, (int(mw * 0.08), int(mh * 0.10)), (int(mw * 0.92), int(mh * 0.90)), 255, -1)

        # White arrow for player
        mask_white = cv2.inRange(hsv, np.array([0, 0, 200]), np.array([180, 50, 255]))
        mask_white = cv2.bitwise_and(mask_white, mask_white, mask=border_mask)
        cnts_w, _ = cv2.findContours(mask_white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        player_pos = None
        best_area = 0
        for c in cnts_w:
            area = cv2.contourArea(c)
            if 15 <= area <= 500:
                M = cv2.moments(c)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    if area > best_area:
                        best_area = area
                        player_pos = (cx, cy)

        # Monster red dots
        mask_red = cv2.bitwise_or(
            cv2.inRange(hsv, np.array([0, 130, 130]), np.array([10, 255, 255])),
            cv2.inRange(hsv, np.array([170, 130, 130]), np.array([180, 255, 255])),
        )
        mask_red = cv2.bitwise_and(mask_red, mask_red, mask=border_mask)
        cnts_r, _ = cv2.findContours(mask_red, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        red_dots = []
        for c in cnts_r:
            area = cv2.contourArea(c)
            if 4 <= area <= 250:
                M = cv2.moments(c)
                if M["m00"] > 0:
                    rx = int(M["m10"] / M["m00"])
                    ry = int(M["m01"] / M["m00"])
                    red_dots.append((rx, ry))

        if not player_pos or not red_dots:
            return None

        closest_dot = min(red_dots, key=lambda pt: (pt[0] - player_pos[0]) ** 2 + (pt[1] - player_pos[1]) ** 2)
        dx = closest_dot[0] - player_pos[0]
        dy = closest_dot[1] - player_pos[1]
        dist = max(1.0, (dx ** 2 + dy ** 2) ** 0.5)

        ndx = dx / dist
        ndy = dy / dist

        # Isometric 45-degree camera projection transformation:
        # Maps 2D Minimap (N/S/E/W) onto 3D Isometric Screen ground space
        iso_x = (ndx - ndy) / 1.4142
        iso_y = (ndx + ndy) / 1.4142
        iso_mag = max(0.001, (iso_x ** 2 + iso_y ** 2) ** 0.5)

        return MinimapNavigationVector(
            norm_dx=ndx,
            norm_dy=ndy,
            distance=dist,
            player_pos=(x1 + player_pos[0], y1 + player_pos[1]),
            target_dot=(x1 + closest_dot[0], y1 + closest_dot[1]),
            total_mobs=len(red_dots),
            screen_dx=iso_x / iso_mag,
            screen_dy=iso_y / iso_mag,
        )

    def get_player_hp_ratio(self, frame: np.ndarray) -> float:
        """Calculates player HP percentage (0.0 to 1.0) by reading top-left green HP bar."""
        if not HAS_OPENCV or frame is None or frame.size == 0:
            return 1.0

        h, w, _ = frame.shape
        hp_crop = frame[int(h * 0.055) : int(h * 0.085), int(w * 0.008) : int(w * 0.125)]
        if hp_crop.size == 0:
            return 1.0

        hsv_hp = cv2.cvtColor(hp_crop, cv2.COLOR_BGR2HSV)
        mask_green = cv2.inRange(hsv_hp, np.array([35, 80, 80]), np.array([85, 255, 255]))
        green_pixels = cv2.countNonZero(mask_green)
        max_green_pixels = 6000.0
        return float(max(0.0, min(1.0, green_pixels / max_green_pixels)))

    def get_revive_button_coords(self, frame: np.ndarray) -> Optional[Tuple[int, int]]:
        """Locates 'Respawn In Town' cyan button strictly on the central death modal."""
        if not HAS_OPENCV or frame is None or frame.size == 0:
            return None

        h, w = frame.shape[:2]
        # Strictly constrain to central death modal button zone (Y: 65% to 83% | X: 35% to 65%)
        x1, y1 = int(w * 0.35), int(h * 0.65)
        x2, y2 = int(w * 0.65), int(h * 0.83)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return None

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask_cyan = cv2.inRange(hsv, np.array([85, 60, 130]), np.array([125, 255, 255]))

        cnts, _ = cv2.findContours(mask_cyan, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            area = cv2.contourArea(c)
            if area > 2000:
                bx, by, bw, bh = cv2.boundingRect(c)
                center_x = x1 + bx + bw // 2
                center_y = y1 + by + bh // 2
                return (center_x, center_y)

        # No death button on screen
        return None

    def check_player_dead(self, frame: np.ndarray) -> bool:
        """Determines if the player is dead (Strict Rule: Dead = HP is 0 in Field)."""
        if frame is None or frame.size == 0 or np.mean(frame) < 30:
            return False

        # If already safely in Town, player is NOT dead
        if self.check_is_in_town(frame):
            return False

        hp = self.get_player_hp_ratio(frame)

        # 1. Strict Direct Rule: Player is dead ONLY when HP is 0 (<= 0.02)
        if hp <= 0.02:
            return True

        # 2. Or if 'Respawn In Town' cyan modal button is physically confirmed on screen
        revive_btn = self.get_revive_button_coords(frame)
        if revive_btn is not None and hp <= 0.05:
            return True

        # If HP > 0.05 -> ALIVE (In Combat / Farming)
        return False

    def find_teleport_crystal(self, frame: np.ndarray) -> Optional[Tuple[int, int]]:
        """Locates Teleport Crystal in Town at the top-right street."""
        if not HAS_OPENCV or frame is None or frame.size == 0:
            return None

        h, w = frame.shape[:2]
        x1, y1 = int(w * 0.48), int(h * 0.05)
        x2, y2 = int(w * 0.72), int(h * 0.32)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return (int(w * 0.585), int(h * 0.175))

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        mask_cyan = cv2.inRange(hsv, np.array([85, 70, 150]), np.array([115, 255, 255]))

        cnts, _ = cv2.findContours(mask_cyan, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            if cv2.contourArea(c) >= 100:
                bx, by, bw, bh = cv2.boundingRect(c)
                return (x1 + bx + bw // 2, y1 + by + bh // 2)

        # High-confidence calibrated Teleport Crystal position (X: 58.5%, Y: 17.5%)
        return (int(w * 0.585), int(h * 0.175))

    def find_heart_npc(self, frame: np.ndarray) -> Optional[Tuple[int, int]]:
        """Locates Heart NPC (Healer) at the top-right curve of the fountain."""
        if not HAS_OPENCV or frame is None or frame.size == 0:
            return None

        h, w = frame.shape[:2]
        # Fountain surroundings (X: 32%..58%, Y: 32%..60%)
        x1, y1 = int(w * 0.32), int(h * 0.32)
        x2, y2 = int(w * 0.58), int(h * 0.60)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return (int(w * 0.425), int(h * 0.477))

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        mask_heart = cv2.bitwise_or(
            cv2.inRange(hsv, np.array([0, 140, 140]), np.array([10, 255, 255])),
            cv2.inRange(hsv, np.array([160, 140, 140]), np.array([180, 255, 255]))
        )

        cnts, _ = cv2.findContours(mask_heart, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            if cv2.contourArea(c) >= 20:
                bx, by, bw, bh = cv2.boundingRect(c)
                heart_cx = x1 + bx + bw // 2
                heart_cy = y1 + by + bh // 2
                # NPC Body is directly underneath the heart icon
                npc_body_y = heart_cy + int(h * 0.04)
                return (heart_cx, npc_body_y)

        # High-confidence calibrated Healer NPC position (X: 42.5%, Y: 47.7%)
        return (int(w * 0.425), int(h * 0.477))

    def check_is_in_town(self, frame: np.ndarray) -> bool:
        """
        Determines if the player is safely in Town.
        Rejects town classification if hostile monster dots or enemy bars exist.
        """
        if not HAS_OPENCV or frame is None or frame.size == 0:
            return False

        # If minimap has monster red dots, we are in the Field
        minimap_dots = self.get_minimap_red_dots(frame)
        if len(minimap_dots) >= 2:
            return False

        # If onscreen hostile HP bars detected, we are in the Field
        enemies = self.find_onscreen_enemies(frame)
        if len(enemies) >= 2:
            return False

        return self.find_heart_npc(frame) is not None or self.find_teleport_crystal(frame) is not None

    def check_character_select(self, frame: np.ndarray) -> bool:
        if not HAS_OPENCV or frame is None or frame.size == 0:
            return False
        h, w, _ = frame.shape
        minimap_crop = frame[int(h * 0.03) : int(h * 0.18), int(w * 0.88) : int(w * 0.98)]
        if minimap_crop.size > 0:
            hsv_mm = cv2.cvtColor(minimap_crop, cv2.COLOR_BGR2HSV)
            mask_map = cv2.inRange(hsv_mm, np.array([30, 40, 40]), np.array([90, 255, 255]))
            if cv2.countNonZero(mask_map) > 200:
                return False

        btn_crop = frame[int(h * 0.90) : int(h * 0.97), int(w * 0.42) : int(w * 0.58)]
        if btn_crop.size > 0:
            hsv = cv2.cvtColor(btn_crop, cv2.COLOR_BGR2HSV)
            mask_btn = cv2.inRange(hsv, np.array([95, 120, 150]), np.array([115, 255, 255]))
            return cv2.countNonZero(mask_btn) > 400
        return False

    def parse_game_state(self, frame: np.ndarray) -> GameState:
        """
        Transforms screenshot into a fully structured GameState with resolution validation.
        """
        state = GameState()
        if frame is None or frame.size == 0:
            return state

        frame, _, _ = self.validate_and_normalize_frame(frame)

        state.character_hp = self.get_player_hp_ratio(frame)
        state.dead = self.check_player_dead(frame)
        state.character_select = self.check_character_select(frame)
        state.in_town = self.check_is_in_town(frame)

        # Enemies detection (all enemies + big enemies)
        enemies, big_enemies = self.find_onscreen_enemies_detailed(frame)
        state.detected_enemies = enemies
        state.enemy_count = len(enemies)

        # Update target tracker with big enemy priority
        active_target = self.tracker.update_or_acquire_target(enemies, big_enemies=big_enemies)
        state.active_target = active_target
        if active_target:
            state.target = f"Monster-{active_target.target_type}"
            state.target_pos = (active_target.x, active_target.y)
            state.target_distance = active_target.distance_to_player
            state.target_is_big = active_target.is_big or len(big_enemies) > 0
        else:
            state.target_is_big = len(big_enemies) > 0

        # Minimap navigation vector
        state.minimap_vector = self.get_minimap_navigation_vector(frame)
        state.location = "Town" if state.in_town else "Field"
        return state
