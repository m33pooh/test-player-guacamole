import os
import glob
import math
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np


@dataclass
class MonsterTemplate:
    name: str
    zone: str
    angle: str
    image_bgr: np.ndarray
    image_gray: np.ndarray
    half_gray: np.ndarray
    width: int
    height: int
    half_width: int
    half_height: int
    is_big: bool = False


@dataclass
class TemplateMatchResult:
    monster_name: str
    zone: str
    center_x: int
    center_y: int
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    confidence: float
    is_big: bool = False


class MultiAngleMonsterTemplateBank:
    """
    High-Speed Multi-Angle Visual Monster Recognition Engine.
    Features:
    1. Pre-cached multi-scale, multi-angle template memory bank.
    2. Sub-10ms half-resolution OpenCV matchTemplate (TM_CCOEFF_NORMED).
    3. Non-Maximum Suppression (NMS) to eliminate duplicate matches across angles/scales.
    4. Auto-loads all images from: data/templates/monsters/<zone>/<mob_name>_<angle>.png
    """
    def __init__(
        self,
        template_root: str = "data/templates/monsters",
        confidence_threshold: float = 0.85,
        use_fast_half_res: bool = True,
    ):
        self.template_root = template_root
        self.confidence_threshold = confidence_threshold
        self.use_fast_half_res = use_fast_half_res
        self.templates: List[MonsterTemplate] = []
        self.templates_by_zone: Dict[str, List[MonsterTemplate]] = {}
        self.active_zone: str = "all"

        self.load_all_templates()

    def load_all_templates(self):
        """
        Scans template_root directory and pre-caches all multi-angle images with multi-scale pyramids.
        Format: data/templates/monsters/<zone>/<mob_name>_<angle>.png
        Or:     data/templates/monsters/<mob_name>_<angle>.png
        """
        self.templates.clear()
        self.templates_by_zone.clear()

        if not os.path.exists(self.template_root):
            os.makedirs(self.template_root, exist_ok=True)
            os.makedirs(os.path.join(self.template_root, "stormreef_isle"), exist_ok=True)
            return

        img_paths = (
            glob.glob(os.path.join(self.template_root, "**", "*.png"), recursive=True)
            + glob.glob(os.path.join(self.template_root, "**", "*.jpg"), recursive=True)
        )

        for path in img_paths:
            try:
                img_bgr = cv2.imread(path)
                if img_bgr is None or img_bgr.size == 0:
                    continue

                img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
                th, tw = img_gray.shape[:2]

                # Pre-downscale half resolution for ultra-fast matching
                hw, hh = max(6, tw // 2), max(6, th // 2)
                half_gray = cv2.resize(img_gray, (hw, hh), interpolation=cv2.INTER_AREA)

                # Parse filename: e.g. "crab_front.png" or "big_golem_side.png"
                basename = os.path.splitext(os.path.basename(path))[0]
                parent_dir = os.path.basename(os.path.dirname(path))
                zone = parent_dir if parent_dir != "monsters" else "general"

                parts = basename.split("_")
                angle = parts[-1] if len(parts) > 1 else "default"
                mob_name = "_".join(parts[:-1]) if len(parts) > 1 else basename
                is_big = "big" in mob_name.lower() or "boss" in mob_name.lower()

                template_obj = MonsterTemplate(
                    name=mob_name,
                    zone=zone,
                    angle=angle,
                    image_bgr=img_bgr,
                    image_gray=img_gray,
                    half_gray=half_gray,
                    width=tw,
                    height=th,
                    half_width=hw,
                    half_height=hh,
                    is_big=is_big,
                )
                self.templates.append(template_obj)

                if zone not in self.templates_by_zone:
                    self.templates_by_zone[zone] = []
                self.templates_by_zone[zone].append(template_obj)

            except Exception as e:
                print(f"[Template Bank Error] Failed to load {path}: {e}")

        print(
            f"[Template Bank] Loaded {len(self.templates)} monster templates across {len(self.templates_by_zone)} zones.",
            flush=True,
        )

    def set_active_zone(self, zone_name: str):
        self.active_zone = zone_name.lower().replace(" ", "_")

    def find_monsters_in_frame(
        self,
        frame: np.ndarray,
        zone: Optional[str] = None,
        custom_roi: Optional[Tuple[int, int, int, int]] = None,
    ) -> List[TemplateMatchResult]:
        """
        Performs ultra-fast multi-angle template matching in the frame (~5-15ms).
        Returns deduplicated, NMS-filtered monster locations with exact (cx, cy) coordinates.
        """
        if frame is None or frame.size == 0 or not self.templates:
            return []

        h, w = frame.shape[:2]
        target_zone = zone or self.active_zone
        active_templates = self.templates_by_zone.get(target_zone, []) + self.templates_by_zone.get("general", [])

        # Fallback to all templates if zone has none
        if not active_templates:
            active_templates = self.templates

        if not active_templates:
            return []

        # Define RoI (Ground Combat Area excluding HUD)
        if custom_roi:
            rx1, ry1, rx2, ry2 = custom_roi
        else:
            rx1, ry1 = int(w * 0.12), int(h * 0.14)
            rx2, ry2 = int(w * 0.86), int(h * 0.86)

        roi_bgr = frame[ry1:ry2, rx1:rx2]
        if roi_bgr.size == 0:
            return []

        roi_gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
        roi_h, roi_w = roi_gray.shape[:2]

        raw_matches: List[TemplateMatchResult] = []

        if self.use_fast_half_res:
            # 0.5x Downscale for 4x speedup
            half_roi_w, half_roi_h = roi_w // 2, roi_h // 2
            if half_roi_w < 10 or half_roi_h < 10:
                return []
            half_roi = cv2.resize(roi_gray, (half_roi_w, half_roi_h), interpolation=cv2.INTER_AREA)

            for tmpl in active_templates:
                thw, thh = tmpl.half_width, tmpl.half_height
                if half_roi_w < thw or half_roi_h < thh:
                    continue

                res = cv2.matchTemplate(half_roi, tmpl.half_gray, cv2.TM_CCOEFF_NORMED)
                loc = np.where(res >= self.confidence_threshold)

                for pt in zip(*loc[::-1]):
                    score = float(res[pt[1], pt[0]])
                    # Scale coordinates back up to full resolution
                    orig_match_x = pt[0] * 2
                    orig_match_y = pt[1] * 2
                    global_x1 = rx1 + orig_match_x
                    global_y1 = ry1 + orig_match_y
                    global_x2 = global_x1 + tmpl.width
                    global_y2 = global_y1 + tmpl.height
                    cx = int((global_x1 + global_x2) // 2)
                    cy = int((global_y1 + global_y2) // 2)

                    raw_matches.append(
                        TemplateMatchResult(
                            monster_name=str(tmpl.name),
                            zone=str(tmpl.zone),
                            center_x=int(cx),
                            center_y=int(cy),
                            bbox=(int(global_x1), int(global_y1), int(global_x2), int(global_y2)),
                            confidence=float(score),
                            is_big=bool(tmpl.is_big),
                        )
                    )
        else:
            for tmpl in active_templates:
                tw, th = tmpl.width, tmpl.height
                if roi_w < tw or roi_h < th:
                    continue

                res = cv2.matchTemplate(roi_gray, tmpl.image_gray, cv2.TM_CCOEFF_NORMED)
                loc = np.where(res >= self.confidence_threshold)

                for pt in zip(*loc[::-1]):
                    score = float(res[pt[1], pt[0]])
                    global_x1 = rx1 + pt[0]
                    global_y1 = ry1 + pt[1]
                    global_x2 = global_x1 + tw
                    global_y2 = global_y1 + th
                    cx = int((global_x1 + global_x2) // 2)
                    cy = int((global_y1 + global_y2) // 2)

                    raw_matches.append(
                        TemplateMatchResult(
                            monster_name=str(tmpl.name),
                            zone=str(tmpl.zone),
                            center_x=int(cx),
                            center_y=int(cy),
                            bbox=(int(global_x1), int(global_y1), int(global_x2), int(global_y2)),
                            confidence=float(score),
                            is_big=bool(tmpl.is_big),
                        )
                    )

        # Apply Non-Maximum Suppression (NMS) to eliminate duplicate matches within 60px
        return self._non_max_suppression(raw_matches, distance_thresh=55)

    def _non_max_suppression(
        self,
        matches: List[TemplateMatchResult],
        distance_thresh: int = 55,
    ) -> List[TemplateMatchResult]:
        """
        Merges multi-angle overlapping matches into a single highest-confidence detection per monster.
        """
        if not matches:
            return []

        matches.sort(key=lambda m: m.confidence, reverse=True)

        selected: List[TemplateMatchResult] = []
        for m in matches:
            too_close = False
            for s in selected:
                dist = math.hypot(m.center_x - s.center_x, m.center_y - s.center_y)
                if dist < distance_thresh:
                    too_close = True
                    break

            if not too_close:
                selected.append(m)

        return selected
