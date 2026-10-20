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
    1. YOLOv11 inference if weight file exists in models/
    2. Fast OpenCV HSV contour / cluster segmentation fallback (< 10ms)
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
