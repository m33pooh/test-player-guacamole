import glob
import os
from typing import Dict, List, Optional, Tuple, Any
import cv2
import numpy as np

try:
    from ultralytics import YOLO
    HAS_YOLO = True
except ImportError:
    HAS_YOLO = False


class MobDetector:
    """
    High-speed monster and elite boss detection module.
    Supports:
    1. Multi-template matching of exact monster sprites (Snails, Spore, Mushrooms, Ribbon Pig)
    2. Real-time floating green HP bar tracking for hit monsters
    3. Fast OpenCV HSV contour / cluster segmentation fallback
    """

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "models", "yolo_maple.pt"
        )
        self.yolo_model = None

        if HAS_YOLO and os.path.exists(self.model_path):
            try:
                self.yolo_model = YOLO(self.model_path)
                print(f"[MobDetector] Loaded YOLOv11 model: {self.model_path}", flush=True)
            except Exception as e:
                print(f"[MobDetector Warning] Could not load YOLO model: {e}", flush=True)

        # Pre-load known monster sprite templates (exact visual memory of map monsters)
        self.templates: List[Tuple[str, np.ndarray, int, int]] = []
        template_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "templates", "monsters"
        )
        if os.path.exists(template_dir):
            for p in sorted(glob.glob(os.path.join(template_dir, "*.png"))):
                t = cv2.imread(p)
                if t is not None:
                    name = os.path.basename(p).split(".")[0].rsplit("_", 1)[0]
                    t_gray = cv2.cvtColor(t, cv2.COLOR_BGR2GRAY)
                    th, tw = t_gray.shape[:2]
                    self.templates.append((name, t_gray, tw, th))
                    # Also include horizontally flipped template for walking left/right
                    self.templates.append((name, cv2.flip(t_gray, 1), tw, th))
            if self.templates:
                print(f"[MobDetector] Loaded {len(self.templates)} monster sprite templates ({template_dir})", flush=True)

        # Pre-load static platform background template for ground-truth zero-mob verification
        self.bg_template: Optional[np.ndarray] = None
        bg_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "templates", "platform_bg.jpg"
        )
        if os.path.exists(bg_path):
            self.bg_template = cv2.imread(bg_path)
            if self.bg_template is not None:
                print(f"[MobDetector] Loaded platform background template: {bg_path}", flush=True)

        # Pet snail tag template for blacklisting (user pet is a snail)
        self.pet_tag_gray: Optional[np.ndarray] = None
        pet_tag_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "templates", "pet_snail_tag.png"
        )
        if os.path.exists(pet_tag_path):
            pt = cv2.imread(pet_tag_path)
            if pt is not None:
                self.pet_tag_gray = cv2.cvtColor(pt, cv2.COLOR_BGR2GRAY)
                print(f"[MobDetector] Loaded pet snail exclusion tag: {pet_tag_path}", flush=True)

        # Visual Bench Landmark (grape arbor) for automatic zero-drift centering
        self.grape_bench: Optional[np.ndarray] = None
        bench_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "templates", "grape_bench.png"
        )
        if os.path.exists(bench_path):
            gb = cv2.imread(bench_path, 0)
            if gb is not None:
                self.grape_bench = gb
                print(f"[MobDetector] Loaded visual bench landmark: {bench_path}", flush=True)

    def detect_clusters_hsv(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Fast heuristic monster cluster detector.
        Identifies active monster clusters on game platforms using color clustering.
        """
        fh, fw, _ = frame.shape
        # Exclude top Minimap (top 25%, left 25%) and bottom HUD (bottom 10%)
        play_area = frame.copy()
        play_area[: int(fh * 0.25), : int(fw * 0.25)] = 0
        play_area[int(fh * 0.90) :, :] = 0

        # Look for monster HP bars or active sprites
        # Small red HP bars over monsters: HSV Red
        hsv = cv2.cvtColor(play_area, cv2.COLOR_BGR2HSV)
        mask1 = cv2.inRange(hsv, np.array([0, 160, 140]), np.array([10, 255, 255]))
        mask2 = cv2.inRange(hsv, np.array([170, 160, 140]), np.array([180, 255, 255]))
        red_mask = cv2.bitwise_or(mask1, mask2)

        contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        points = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 10 <= area <= 400:
                M = cv2.moments(cnt)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    points.append((cx, cy))

        # Cluster points within 120px radius
        clusters: List[Dict[str, Any]] = []
        visited = set()
        for i, (px, py) in enumerate(points):
            if i in visited:
                continue
            group = [(px, py)]
            visited.add(i)
            for j, (ox, oy) in enumerate(points):
                if j not in visited:
                    if ((px - ox) ** 2 + (py - oy) ** 2) ** 0.5 < 140:
                        group.append((ox, oy))
                        visited.add(j)

            avg_x = int(sum(x for x, y in group) / len(group))
            avg_y = int(sum(y for x, y in group) / len(group))
            clusters.append({
                "center_x": avg_x,
                "center_y": avg_y,
                "count": len(group),
                "is_elite": False,
            })

        return clusters

    def detect_monster_hp_bars(
        self,
        frame: np.ndarray,
        facing: str = "right",
        player_center: Tuple[int, int] = (1123, 740),
        max_dist_x: int = 700,
        max_dist_y: int = 150,
        reach_left: Optional[int] = None,
        reach_right: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Detects active green monster HP bars above monsters on platforms.
        Classic MapleStory: When a monster is damaged, an HP gauge appears over its head.
        Green fill: G > 140, R < 110, B < 90, G - R > 40.
        Width: 8px to 85px (full ~76px). Height: 3px to 8px.
        Returns sorted list of HP bars matching the facing direction and island platform range.
        """
        px, py = player_center
        h, w, _ = frame.shape

        if facing == "right":
            limit_x = reach_right if reach_right is not None else 260
            x_min = max(0, px + 135)
            x_max = min(w, px + limit_x)
        else:
            limit_x = reach_left if reach_left is not None else max_dist_x
            x_min = max(0, px - limit_x)
            x_max = min(w, px - 135)

        # Real monster HP bars float in air above monsters on grass (y: 570 to 635)
        # Avoids grape arbor roof/leaves (y < 570) and platform grass blades (y >= 645)
        y_min = max(0, py - 130)
        y_max = min(h, py - 65)

        if x_max <= x_min or y_max <= y_min:
            return []

        roi = frame[y_min:y_max, x_min:x_max]
        if roi.size == 0:
            return []

        r = roi[:, :, 2].astype(int)
        g = roi[:, :, 1].astype(int)
        b = roi[:, :, 0].astype(int)

        green_mask = ((g > 140) & (r < 110) & (b < 90) & ((g - r) > 40)).astype(np.uint8) * 255
        cnts, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        matched_bars = []
        for c in cnts:
            bx, by, bw, bh = cv2.boundingRect(c)
            if 8 <= bw <= 85 and 3 <= bh <= 8:
                abs_x = bx + x_min
                abs_y = by + y_min
                dx = abs_x - px
                dy = abs(abs_y - py)
                hp_percent = min(100.0, max(0.0, (bw / 76.0) * 100.0))
                matched_bars.append({
                    "x": abs_x,
                    "y": abs_y,
                    "width": bw,
                    "height": bh,
                    "hp_percent": round(hp_percent, 1),
                    "distance_x": abs(dx),
                    "distance_y": dy,
                })

        # Sort by horizontal proximity to player
        matched_bars.sort(key=lambda item: item["distance_x"])
        return matched_bars

    def detect_recognized_mobs(
        self,
        roi: np.ndarray,
        px_roi: int,
        r_left: int = 600,
        r_right: int = 260,
        threshold: float = 0.60,
    ) -> List[Dict[str, Any]]:
        """
        High-precision monster recognition using template matching of known map monsters.
        Recognizes exact monster species (Snail, Spore, Orange/Green Mushroom, Ribbon Pig).
        Filters out player/pet on bench and other players outside the island.
        """
        if not self.templates or roi.size == 0:
            return []

        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        detected_boxes = []
        scores = []
        names = []

        for name, t_gray, tw, th in self.templates:
            # Exclude Snail as it is the player's pet
            if "snail" in name.lower():
                continue
            if roi_gray.shape[0] < th or roi_gray.shape[1] < tw:
                continue
            res = cv2.matchTemplate(roi_gray, t_gray, cv2.TM_CCOEFF_NORMED)
            loc = np.where(res >= threshold)
            for pt in zip(*loc[::-1]):
                x, y = pt
                dx = (x + tw // 2) - px_roi
                # Strict boundary filter:
                # 1. Must be on this island platform floor (feet y >= 110 in roi)
                # 2. Exclude wooden bench & grape arbor center [-70, +70] where only player and pet stand
                # 3. Exclude outside island boundaries [-r_left, +r_right]
                if (y + th) >= 110 and ((-r_left <= dx <= -70) or (70 <= dx <= r_right)):
                    detected_boxes.append([x, y, tw, th])
                    scores.append(float(res[y, x]))
                    names.append(name)

        if not detected_boxes:
            return []

        indices = cv2.dnn.NMSBoxes(detected_boxes, scores, score_threshold=threshold, nms_threshold=0.35)
        results = []
        for i in indices:
            idx = int(i.item()) if hasattr(i, "item") else int(i)
            x, y, w, h = detected_boxes[idx]
            dx = (x + w // 2) - px_roi
            results.append({
                "name": names[idx],
                "dx": dx,
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "score": round(scores[idx], 2),
            })

        results.sort(key=lambda m: abs(m["dx"]))
        return results

    def scan_platform_mobs(
        self,
        frame: np.ndarray,
        player_center: Tuple[int, int] = (1065, 700),
        max_reach_x: int = 540,
        reach_left: Optional[int] = None,
        reach_right: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        High-speed computer vision scanner for monsters on current platform.
        Combines:
        1. Exact monster sprite recognition (visual memory)
        2. Floating green monster HP bars
        3. Floor tags and monster bodies
        """
        px, py = player_center
        fh, fw, _ = frame.shape

        # Visual Bench Landmark Auto-Centering (13ms):
        # Uses exact grape arbor visual template to guarantee scanner centers on bench
        if self.grape_bench is not None:
            sy1, sy2 = max(0, int(py - 250)), min(fh, int(py + 100))
            if (sy2 - sy1) >= self.grape_bench.shape[0]:
                search_roi = cv2.cvtColor(frame[sy1:sy2, :], cv2.COLOR_BGR2GRAY)
                res_b = cv2.matchTemplate(search_roi, self.grape_bench, cv2.TM_CCOEFF_NORMED)
                _, max_vb, _, max_lb = cv2.minMaxLoc(res_b)
                if max_vb >= 0.50:
                    px = max_lb[0] + 80
                    py = sy1 + max_lb[1] + 60

        r_left = reach_left if reach_left is not None else 605
        r_right = reach_right if reach_right is not None else 260

        # Compact island bounding box based on user selected area:
        # X: [460, 1325] -> dx: [-605, +260]
        # Y: [495, 710] -> dy: [-200, +10]
        x1 = max(0, px - r_left)
        x2 = min(fw, px + r_right)
        y1 = max(0, py - 200)
        y2 = min(fh, py + 10)

        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return {
                "left": {"active": False, "bars": [], "tags": [], "mobs": [], "count": 0},
                "right": {"active": False, "bars": [], "tags": [], "mobs": [], "count": 0},
                "any_mobs": False,
                "total_count": 0,
                "recognized_mobs": [],
            }

        roi_px = px - x1

        # 0. High-Precision Template Recognition of Actual Monsters (exact visual memory)
        recognized_mobs = self.detect_recognized_mobs(roi, roi_px, r_left=r_left, r_right=r_right, threshold=0.56)
        rec_left = [m for m in recognized_mobs if m["dx"] < 0]
        rec_right = [m for m in recognized_mobs if m["dx"] > 0]

        # 1. Floating Green HP Bars in air above monsters (y: 500 to 625 -> local_y: 0 to 125)
        # Avoids grass line (y >= 645) completely to eliminate grass blade false positives
        sky_local_y2 = min(roi.shape[0], 125)
        sky_roi = roi[:sky_local_y2, :]
        shr = sky_roi[:, :, 2].astype(int)
        shg = sky_roi[:, :, 1].astype(int)
        shb = sky_roi[:, :, 0].astype(int)
        green_mask = ((shg > 135) & (shr < 110) & (shb < 90) & ((shg - shr) > 40)).astype(np.uint8) * 255
        cnts, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        left_bars, right_bars = [], []
        for c in cnts:
            bx, by, bw, bh = cv2.boundingRect(c)
            if 12 <= bw <= 85 and 3 <= bh <= 7 and (bw / float(bh)) >= 2.0:
                dx = bx - roi_px
                # Wooden bench & grape arbor center span dx: [-70, +70]
                if dx <= -70:
                    left_bars.append({"x": x1 + bx, "width": bw, "dx": dx})
                elif dx >= 70:
                    right_bars.append({"x": x1 + bx, "width": bw, "dx": dx})

        def _cluster_count(items: List[Dict[str, Any]], tol: int = 45) -> int:
            if not items:
                return 0
            xs = sorted([it["dx"] for it in items])
            clusters = 1
            last_x = xs[0]
            for x in xs[1:]:
                if (x - last_x) > tol:
                    clusters += 1
                    last_x = x
            return clusters

        # Verified monster indicators per side (Recognized Sprites + Damaged Floating HP Bars)
        l_items = rec_left + left_bars
        r_items = rec_right + right_bars

        l_active = bool(l_items)
        r_active = bool(r_items)

        l_count = _cluster_count(l_items, tol=45) if l_items else 0
        r_count = _cluster_count(r_items, tol=45) if r_items else 0

        total_count = l_count + r_count

        return {
            "left": {"active": l_active, "bars": left_bars, "tags": [], "mobs": rec_left, "count": l_count},
            "right": {"active": r_active, "bars": right_bars, "tags": [], "mobs": rec_right, "count": r_count},
            "any_mobs": l_active or r_active,
            "total_count": total_count,
            "recognized_mobs": recognized_mobs,
        }

    def detect_mobs(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        Executes monster detection.
        Returns mob clusters and elite presence.
        """
        if self.yolo_model is not None:
            try:
                results = self.yolo_model(frame, verbose=False, conf=0.35)[0]
                clusters = []
                elite_present = False
                for box in results.boxes:
                    cls_id = int(box.cls[0])
                    label = self.yolo_model.names.get(cls_id, "")
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
                    is_elite = "elite" in label.lower() or "boss" in label.lower()
                    if is_elite:
                        elite_present = True
                    clusters.append({
                        "center_x": cx,
                        "center_y": cy,
                        "count": 1,
                        "is_elite": is_elite,
                        "bbox": [int(x1), int(y1), int(x2), int(y2)],
                    })
                return {
                    "clusters": clusters,
                    "total_mobs": len(clusters),
                    "elite_present": elite_present,
                }
            except Exception as e:
                print(f"[MobDetector Error] YOLO inference failed: {e}", flush=True)

        # Fallback to heuristic clustering
        clusters = self.detect_clusters_hsv(frame)
        total_count = sum(c["count"] for c in clusters)
        return {
            "clusters": clusters,
            "total_mobs": total_count,
            "elite_present": False,
        }

