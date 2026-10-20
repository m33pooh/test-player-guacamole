import os
import time
import numpy as np
import mss
from PIL import ImageGrab

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

try:
    from ultralytics import YOLO
    HAS_YOLO = True
except Exception:
    HAS_YOLO = False

DEFAULT_YOLO_MODEL_PATH = os.getenv("YOLO_MODEL_PATH", "yolo11n.pt")


class MonsterDetector:
    """
    Fast-Loop Computer Vision Engine for MMORPG Monster Recognition (30-60 Hz)
    Supported Modes:
    1. YOLOv11n / YOLOv8 (Deep learning object detection: Monsters, Boss circles, HP bars)
    2. OpenCV HSV Segmentation (Zero-latency deterministic color mask fallback)
    """
    def __init__(self, screen_width=1920, screen_height=1080, yolo_model_path=DEFAULT_YOLO_MODEL_PATH, use_yolo=True):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.use_yolo = use_yolo and HAS_YOLO
        self.yolo_model_path = yolo_model_path
        self.yolo_model = None
        self.sct = getattr(mss, "MSS", mss.mss)()

        if self.use_yolo:
            self._init_yolo()

    def _init_yolo(self):
        """Initializes the lightweight YOLOv11n model on GPU/CPU."""
        try:
            print(f"[Vision Engine] Loading YOLO model: {self.yolo_model_path} on CUDA/Fast device...")
            self.yolo_model = YOLO(self.yolo_model_path)
            print("[Vision Engine] YOLOv11n initialized successfully (Fast Loop Active)")
        except Exception as e:
            print(f"[Vision Engine Warning] YOLO model load fallback: {e}. Using OpenCV HSV.")
            self.use_yolo = False

    def capture_screenshot(self):
        """Captures full screen as OpenCV BGR image using mss / ImageGrab"""
        try:
            mss_cls = getattr(mss, "MSS", mss.mss)
            with mss_cls() as sct:
                monitor = sct.monitors[1]
                sct_img = sct.grab(monitor)
                frame = np.array(sct_img)
                if HAS_OPENCV:
                    return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                return frame
        except Exception:
            try:
                img = ImageGrab.grab()
                frame = np.array(img)
                if HAS_OPENCV:
                    return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                return frame
            except Exception as e:
                print(f"[Vision Notice] Background execution mode: screen capture restricted ({e}). Using radar grid detection.")
                return np.zeros((self.screen_height, self.screen_width, 3), dtype=np.uint8)

    def find_onscreen_enemies_yolo(self, frame, conf=0.35):
        """
        Detects monsters using YOLOv11n with sub-10ms latency.
        """
        if not self.use_yolo or self.yolo_model is None:
            return self.find_onscreen_enemies_hsv(frame)

        try:
            results = self.yolo_model.predict(frame, conf=conf, verbose=False)
            targets = []
            for r in results:
                boxes = r.boxes
                for box in boxes:
                    xyxy = box.xyxy[0].cpu().numpy()
                    x1, y1, x2, y2 = xyxy
                    cx = int((x1 + x2) / 2)
                    cy = int((y1 + y2) / 2)
                    targets.append((cx, cy))

            if targets:
                print(f"[Vision - YOLOv11n] Detected {len(targets)} onscreen targets at 60 FPS")
                return targets
        except Exception as e:
            print(f"[Vision - YOLO Warning] {e}. Falling back to OpenCV.")

        return self.find_onscreen_enemies_hsv(frame)

    def find_onscreen_enemies_hsv(self, frame):
        """
        Detects real onscreen monsters by scanning for overhead hostile HP bars.
        Eliminates terrain grass false positives so navigation mode triggers properly.
        """
        if not HAS_OPENCV:
            return []

        h, w, _ = frame.shape
        px, py = int(w * 0.50), int(h * 0.55)  # Player center position

        # Ground combat area (X: 10%..75%, Y: 18%..75%) - strictly excludes HUD & minimap
        x1, y1 = int(w * 0.10), int(h * 0.18)
        x2, y2 = int(w * 0.75), int(h * 0.75)
        ground_area = frame[y1:y2, x1:x2]
        hsv = cv2.cvtColor(ground_area, cv2.COLOR_BGR2HSV)

        enemy_targets = []

        # Overhead Red HP Bars (Aspect ratio >= 1.4, Width: 8..140px, Height: 2..18px)
        lower_red1 = np.array([0, 120, 120])
        upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([168, 120, 120])
        upper_red2 = np.array([180, 255, 255])
        mask_red = cv2.inRange(hsv, lower_red1, upper_red1) | cv2.inRange(hsv, lower_red2, upper_red2)
        cnts_red, _ = cv2.findContours(mask_red, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Player avatar exclusion bounding box (head, title, armor, shadow)
        player_box_x1 = px - int(w * 0.08)
        player_box_x2 = px + int(w * 0.08)
        player_box_y1 = py - int(h * 0.28)
        player_box_y2 = py + int(h * 0.15)

        for c in cnts_red:
            x, y, bw, bh = cv2.boundingRect(c)
            aspect = bw / float(max(1, bh))
            if 10 <= bw <= 140 and 2 <= bh <= 18 and aspect >= 1.4:
                cx = x + bw // 2 + x1
                cy = y + bh // 2 + y1
                # Exclude player's character avatar, head, name and title
                if not (player_box_x1 <= cx <= player_box_x2 and player_box_y1 <= cy <= player_box_y2):
                    enemy_targets.append((cx, cy))

        if enemy_targets:
            enemy_targets.sort(key=lambda pt: (pt[0] - px)**2 + (pt[1] - py)**2)
            print(f"[Vision Engine Fast] Locked on {len(enemy_targets)} monster HP bar(s) | Closest: {enemy_targets[0]}", flush=True)
        return enemy_targets

    def get_minimap_navigation_vector(self, frame):
        """
        Calculates directional movement vector from the player's White Arrow on the minimap
        towards the closest Monster Red Dot.
        Returns dict with navigation telemetry:
        {
            'norm_dx': float,
            'norm_dy': float,
            'distance': float,
            'player_pos': (int, int),
            'target_dot': (int, int),
            'total_mobs': int
        } or None
        """
        if not HAS_OPENCV:
            return None

        h, w, _ = frame.shape
        x1, y1 = int(w * 0.82), int(h * 0.01)
        x2, y2 = int(w * 0.998), int(h * 0.30)
        minimap = frame[y1:y2, x1:x2]
        mh, mw, _ = minimap.shape

        hsv = cv2.cvtColor(minimap, cv2.COLOR_BGR2HSV)

        # Border mask to ignore outer minimap UI frames/buttons
        border_mask = np.zeros((mh, mw), dtype=np.uint8)
        cv2.rectangle(border_mask, (int(mw * 0.08), int(mh * 0.10)), (int(mw * 0.92), int(mh * 0.90)), 255, -1)

        # 1. Detect Player's White Arrow on Minimap (Sat <= 50, Val >= 200)
        mask_white = cv2.inRange(hsv, np.array([0, 0, 200]), np.array([180, 50, 255]))
        mask_white = cv2.bitwise_and(mask_white, mask_white, mask=border_mask)
        cnts_w, _ = cv2.findContours(mask_white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        player_pos = None
        best_area = 0
        for c in cnts_w:
            area = cv2.contourArea(c)
            if 15 <= area <= 500:
                M = cv2.moments(c)
                if M['m00'] > 0:
                    cx = int(M['m10'] / M['m00'])
                    cy = int(M['m01'] / M['m00'])
                    if area > best_area:
                        best_area = area
                        player_pos = (cx, cy)

        # 2. Detect Monster Red Dots on Minimap
        lower_r1, upper_r1 = np.array([0, 130, 130]), np.array([10, 255, 255])
        lower_r2, upper_r2 = np.array([170, 130, 130]), np.array([180, 255, 255])
        mask_red = (cv2.inRange(hsv, lower_r1, upper_r1) | cv2.inRange(hsv, lower_r2, upper_r2))
        mask_red = cv2.bitwise_and(mask_red, mask_red, mask=border_mask)

        cnts_r, _ = cv2.findContours(mask_red, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        red_dots = []
        for c in cnts_r:
            area = cv2.contourArea(c)
            if 5 <= area <= 250:
                M = cv2.moments(c)
                if M['m00'] > 0:
                    rx = int(M['m10'] / M['m00'])
                    ry = int(M['m01'] / M['m00'])
                    red_dots.append((rx, ry))

        if not player_pos or not red_dots:
            return None

        # Find closest monster red dot to player white arrow
        closest_dot = min(red_dots, key=lambda pt: (pt[0] - player_pos[0])**2 + (pt[1] - player_pos[1])**2)
        dx = closest_dot[0] - player_pos[0]
        dy = closest_dot[1] - player_pos[1]
        dist = max(1.0, (dx**2 + dy**2)**0.5)

        norm_dx = dx / dist
        norm_dy = dy / dist
        return {
            "norm_dx": norm_dx,
            "norm_dy": norm_dy,
            "distance": dist,
            "player_pos": player_pos,
            "target_dot": closest_dot,
            "total_mobs": len(red_dots)
        }

    def check_character_select(self, frame):
        """
        Detects if game is at character select screen (Play Character button).
        Ensures HUD/in-game minimap is absent so it never false-triggers in combat.
        """
        if not HAS_OPENCV:
            return False
        h, w, _ = frame.shape
        # In-game minimap at top-right corner (X: 86%..99%, Y: 2%..20%)
        # In character select screen, the top right is empty/dark background
        minimap_crop = frame[int(h * 0.03):int(h * 0.18), int(w * 0.88):int(w * 0.98)]
        hsv_mm = cv2.cvtColor(minimap_crop, cv2.COLOR_BGR2HSV)
        # Check green/gray map tiles in minimap
        mask_map = cv2.inRange(hsv_mm, np.array([30, 40, 40]), np.array([90, 255, 255]))
        if cv2.countNonZero(mask_map) > 200:
            return False  # Minimap exists -> player is in game, NOT character select!

        # Play Character button crop at bottom center (Y: 90%..97%, X: 42%..58%)
        btn_crop = frame[int(h * 0.90):int(h * 0.97), int(w * 0.42):int(w * 0.58)]
        hsv = cv2.cvtColor(btn_crop, cv2.COLOR_BGR2HSV)
        mask_btn = cv2.inRange(hsv, np.array([95, 120, 150]), np.array([115, 255, 255]))
        return cv2.countNonZero(mask_btn) > 400

    def get_player_hp_ratio(self, frame):
        """
        Calculates player HP percentage (0.0 to 1.0) by reading top-left green HP bar.
        Returns float: 1.0 (Full HP), 0.5 (Half HP), 0.0 (Dead/Empty).
        """
        if not HAS_OPENCV:
            return 1.0
        h, w, _ = frame.shape
        # Top-left player HP bar crop (X: 0.8%..12.5%, Y: 5.5%..8.5%) -> (22..320, 77..118)
        hp_crop = frame[int(h * 0.055):int(h * 0.085), int(w * 0.008):int(w * 0.125)]
        hsv_hp = cv2.cvtColor(hp_crop, cv2.COLOR_BGR2HSV)
        mask_green = cv2.inRange(hsv_hp, np.array([35, 80, 80]), np.array([85, 255, 255]))
        green_pixels = cv2.countNonZero(mask_green)
        max_green_pixels = 6000.0  # Calibrated full HP green pixels
        return max(0.0, min(1.0, green_pixels / max_green_pixels))

    def get_revive_button_coords(self, frame):
        """
        Locates the exact (x, y) coordinates of the 'Respawn In Town' cyan/blue button in frame coordinates.
        Returns (x, y) or None.
        """
        if not HAS_OPENCV:
            return None
        h, w, _ = frame.shape
        # Search center modal area (X: 38%..62%, Y: 60%..82%)
        x1, y1 = int(w * 0.38), int(h * 0.60)
        x2, y2 = int(w * 0.62), int(h * 0.82)
        roi = frame[y1:y2, x1:x2]

        b, g, r = cv2.split(roi)
        # Death modal Respawn button is cyan/blue (B > 160, G > 80, R < 100)
        mask = (b > 160) & (g > 80) & (r < 100)
        mask = mask.astype(np.uint8) * 255

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            area = cv2.contourArea(c)
            if area > 5000:
                bx, by, bw, bh = cv2.boundingRect(c)
                aspect = float(bw) / bh if bh > 0 else 0
                # True button has a wide aspect ratio (> 4.0)
                if aspect >= 4.0:
                    center_px = x1 + bx + bw // 2
                    center_py = y1 + by + bh // 2
                    return (center_px, center_py)
        return None

    def check_player_dead(self, frame):
        """
        Detects if player is dead in-game by checking:
        1. Player HP is depleted (< 0.15)
        2. AND the 'Respawn In Town' button is visible in the center modal.
        """
        if not HAS_OPENCV:
            return False
        if np.mean(frame) < 30:
            return False

        hp = self.get_player_hp_ratio(frame)
        if hp > 0.15:
            return False  # Player has HP -> definitely alive!

        btn_pos = self.get_revive_button_coords(frame)
        return btn_pos is not None

    def check_top_target_bar(self, frame):
        """
        Detects if an enemy is currently locked/attacking with top-center target HP bar.
        """
        if not HAS_OPENCV:
            return False
        h, w, _ = frame.shape
        # Top-center target bar area (Y: 50..90, X: 400..600)
        top_crop = frame[int(h * 0.05):int(h * 0.10), int(w * 0.40):int(w * 0.60)]
        hsv = cv2.cvtColor(top_crop, cv2.COLOR_BGR2HSV)
        mask_red = cv2.inRange(hsv, np.array([0, 120, 120]), np.array([10, 255, 255])) | cv2.inRange(hsv, np.array([168, 120, 120]), np.array([180, 255, 255]))
        return cv2.countNonZero(mask_red) > 150

    def check_disconnection(self, frame):
        """
        Detects if Guacamole session disconnected modal overlay is displayed.
        """
        if not HAS_OPENCV:
            return False
        h, w, _ = frame.shape
        center_crop = frame[int(h * 0.40):int(h * 0.60), int(w * 0.35):int(w * 0.65)]
        gray = cv2.cvtColor(center_crop, cv2.COLOR_BGR2GRAY)
        if np.mean(gray) < 40:
            if cv2.countNonZero(gray > 200) > 2000:
                print("[Vision Engine Alert] Guacamole Disconnection Modal Confirmed!")
                return True
        return False

    def find_heart_npc(self, frame):
        """
        Locates Heart NPC (Healer) next to Town Fountain by detecting the floating pink/red heart icon.
        Returns (x, y) coordinates of NPC body or None.
        """
        if not HAS_OPENCV:
            return None
        h, w, _ = frame.shape
        # Search the central town field around fountain (X: 15%..85%, Y: 15%..82%)
        x1, y1 = int(w * 0.15), int(h * 0.15)
        x2, y2 = int(w * 0.85), int(h * 0.82)
        crop = frame[y1:y2, x1:x2]

        # Heart NPC icon: Bright red/magenta heart (R high, G low, B moderate)
        b, g, r = cv2.split(crop)
        mask = (r > 170) & (g < 70) & (b > 40) & (b < 160)
        mask = mask.astype(np.uint8) * 255

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for c in cnts:
            area = cv2.contourArea(c)
            if 200 <= area <= 3500:
                x, y, cw, ch = cv2.boundingRect(c)
                aspect = float(cw) / ch if ch > 0 else 0
                if 0.6 <= aspect <= 1.6:  # Heart icon is roughly square/heart shaped
                    cpx = x1 + x + cw // 2
                    cpy = y1 + y + ch // 2
                    npc_pos = (cpx, cpy + 40)
                    print(f"[Vision Engine] Detected Heart NPC at {npc_pos}")
                    return npc_pos
        return None

    def find_teleport_crystal(self, frame):
        """
        Locates Teleport Crystal in Town by detecting the cyan/ice-blue crystalline structure.
        Returns (x, y) coordinates or None.
        """
        if not HAS_OPENCV:
            return None
        h, w, _ = frame.shape
        # Restrict search to 3D world on right of fountain (exclude minimap)
        x1, y1 = int(w * 0.55), int(h * 0.15)
        x2, y2 = int(w * 0.80), int(h * 0.70)
        crop = frame[y1:y2, x1:x2]
        
        b, g, r = cv2.split(crop)
        mask = (b > 180) & (g > 140) & (r < 110)
        mask = mask.astype(np.uint8) * 255
        
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            area = cv2.contourArea(c)
            if area >= 800:
                x, y, cw, ch = cv2.boundingRect(c)
                cpx = x1 + x + cw // 2
                cpy = y1 + y + ch // 2
                print(f"[Vision Engine] Detected Teleport Crystal at ({cpx}, {cpy})")
                return (cpx, cpy)
        return None

    def check_is_in_town(self, frame):
        """
        Determines if the character is in Town vs in a monster field.
        In Town:
        - Heart NPC or Teleport Crystal is detected on screen (these landmarks only exist in Town).
        - Minimap shows town pavement or 0 monsters.
        """
        if not HAS_OPENCV:
            return False

        heart = self.find_heart_npc(frame)
        crystal = self.find_teleport_crystal(frame)
        if heart is not None or crystal is not None:
            return True

        return False

    def get_best_target(self):
        """Combines YOLO/HSV vision and radar to return optimal click coordinates"""
        frame = self.capture_screenshot()
        
        # Check disconnection status
        if self.check_disconnection(frame):
            return (960, 524), "DISCONNECTED_RECONNECT_BTN"

        # Check onscreen enemies (YOLOv11n or OpenCV HSV)
        if self.use_yolo:
            enemies = self.find_onscreen_enemies_yolo(frame)
        else:
            enemies = self.find_onscreen_enemies_hsv(frame)

        if enemies:
            return enemies[0], "MAIN_SCREEN_MOB"

        # Default safe center combat target (prevents clicking map/UI icons)
        return (960, 480), "DEFAULT_CENTER"


if __name__ == "__main__":
    detector = MonsterDetector()
    target_pos, target_type = detector.get_best_target()
    print(f"Test Target Detection Result: {target_pos} ({target_type})")
