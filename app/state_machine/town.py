import time
from typing import Optional, Tuple

from app.controller.controller import ActionController
from app.vision.detector import FastVisionDetector
from app.vision.vlm import QwenVLStrategicBrain
from config.settings import GameCoordsConfig


class TownStateHandler:
    """
    Town interaction, Healing at Heart NPC, and Teleport Crystal Warp Handler.
    Exact Sequence (Double-Click Only - No F Key Needed):
    1. Double-click Heart NPC on left of fountain -> Wait 3.5s to walk there -> Double-click to heal HP to 100%.
    2. Double-click Teleport Crystal on right of fountain -> Wait 4.0s to walk there -> Double-click to open Warp menu.
    3. Select destination zone (Stormreef Isle Lv61-65).
    4. Click green Warp button -> Transition back to IN_FIELD.
    """
    def __init__(
        self,
        controller: ActionController,
        coords: Optional[GameCoordsConfig] = None,
        detector: Optional[FastVisionDetector] = None,
        vlm: Optional[QwenVLStrategicBrain] = None,
    ):
        self.controller = controller
        self.coords = coords or GameCoordsConfig()
        self.detector = detector
        self.vlm = vlm
        self.last_heal_time = 0.0

    def heal_at_heart_npc(self, frame=None, target_coords: Optional[Tuple[int, int]] = None) -> bool:
        """
        Walks to Heart NPC by double-clicking, and double-clicks again to fully restore HP.
        """
        print("[Town State] Restoring character HP with Heart NPC (Healer)...", flush=True)
        self.controller.press("escape", delay=0.1)

        npc_pos = target_coords
        if not npc_pos and self.detector and frame is not None:
            npc_pos = self.detector.find_heart_npc(frame)

        if not npc_pos and self.vlm and frame is not None:
            v_res = self.vlm.query_town_healer_and_crystal(frame)
            if v_res.get("healer_visible") and v_res.get("healer_x") and v_res.get("healer_y"):
                npc_pos = (int(v_res["healer_x"]), int(v_res["healer_y"]))

        # 2-Step Town Fountain Pathing (Walks to right courtyard first to avoid getting stuck on fountain wall)
        if frame is not None:
            h, w = frame.shape[:2]
            courtyard_x, courtyard_y = int(w * 0.71), int(h * 0.44)
            healer_x, healer_y = int(w * 0.76), int(h * 0.15)
        else:
            courtyard_x, courtyard_y = 1320, 480
            healer_x, healer_y = 1420, 160

        print(f"[Town State] Step 1: Walking to fountain right courtyard at ({courtyard_x}, {courtyard_y})...", flush=True)
        self.controller.dblclick(courtyard_x, courtyard_y)
        time.sleep(2.5)

        print(f"[Town State] Step 2: Double-clicking Heart NPC at ({healer_x}, {healer_y}) to heal HP...", flush=True)
        self.controller.dblclick(healer_x, healer_y)
        time.sleep(2.5)
        self.controller.dblclick(healer_x, healer_y)
        time.sleep(0.5)
        self.controller.press("f", delay=0.1)
        self.controller.press("5", delay=0.05)
        time.sleep(0.8)

        self.last_heal_time = time.time()
        print("[Town State] Character HP fully restored.", flush=True)
        return True

    def interact_teleport_crystal(self, frame=None, target_coords: Optional[Tuple[int, int]] = None) -> bool:
        """
        Walks to Teleport Crystal by double-clicking, and double-clicks again to open the Crystal Warp UI.
        """
        print("[Town State] Interacting with Teleport Crystal to open World Map...", flush=True)
        self.controller.press("escape", delay=0.15)

        if frame is not None:
            h, w = frame.shape[:2]
            cx, cy = int(w * 0.70), int(h * 0.15)
        else:
            cx, cy = 1300, 160

        print(f"[Town State] Double-clicking Teleport Crystal at ({cx}, {cy})...", flush=True)
        self.controller.dblclick(cx, cy)
        time.sleep(2.5)

        # Double-click Teleport Crystal to open Warp menu
        print(f"[Town State] Double-clicking Teleport Crystal at ({cx}, {cy}) to open Warp menu...", flush=True)
        self.controller.dblclick(cx, cy)
        time.sleep(0.5)
        self.controller.press("f", delay=0.1)
        self.controller.dblclick(cx, cy)
        time.sleep(2.0)
        return True

    def execute_warp_to_zone(self, target_zone_coords: Optional[Tuple[int, int]] = None, frame=None) -> bool:
        """
        Selects zone on World Map and clicks Warp button to return to farming area.
        """
        if frame is not None:
            h, w = frame.shape[:2]
            zone_x, zone_y = int(w * 0.27), int(h * 0.485)
            warp_btn_x, warp_btn_y = int(w * 0.95), int(h * 0.972)
        else:
            zone_x, zone_y = 502, 524
            warp_btn_x, warp_btn_y = 1770, 1050

        print(f"[Town State] Selecting target map zone at ({zone_x}, {zone_y})...", flush=True)
        self.controller.click(zone_x, zone_y)
        time.sleep(1.0)

        print(f"[Town State] Clicking green Warp button at ({warp_btn_x}, {warp_btn_y})...", flush=True)
        self.controller.click(warp_btn_x, warp_btn_y)
        time.sleep(0.3)
        self.controller.click(warp_btn_x, warp_btn_y)

        print("[Town State] Waiting 4.5s for map zone transition...", flush=True)
        time.sleep(4.5)

        # Initial clearance move out of spawn crystal nook towards the open grass field on the left
        if frame is not None:
            h, w = frame.shape[:2]
            open_road_x = int(w * 0.38)
            open_road_y = int(h * 0.75)
            down_road_x = int(w * 0.40)
            down_road_y = int(h * 0.82)
        else:
            open_road_x, open_road_y = 700, 750
            down_road_x, down_road_y = 750, 850

        # Step 1: Walk Down-Left into the open grass field (away from right rock wall)
        print(f"[Town State] Executing post-warp clearance walk to open grass field at ({open_road_x}, {open_road_y})...", flush=True)
        self.controller.dblclick(open_road_x, open_road_y)
        time.sleep(0.3)
        self.controller.press("s", delay=0.2)
        self.controller.press("a", delay=0.2)
        time.sleep(1.2)

        # Step 2: Walk DOWN-LEFT into the main monster valley path
        print(f"[Town State] Walking DOWN-LEFT into the monster field road at ({down_road_x}, {down_road_y})...", flush=True)
        self.controller.dblclick(down_road_x, down_road_y)
        time.sleep(0.2)
        self.controller.press("s", delay=0.4)
        self.controller.press("a", delay=0.2)
        time.sleep(1.8)
        return True

    def execute_town_cycle(self, frame=None) -> bool:
        """
        Executes complete end-to-end Town recovery sequence:
        1. Checks HP: If HP < 0.88, walks to Heart NPC and restores HP to 100%.
           If HP is already full, SKIPS Heart NPC and heads directly to Teleport Crystal!
        2. Double-clicks to walk to Teleport Crystal at top-right -> Interacts to open World Map.
        3. Selects Stormreef Isle and clicks green Warp button.
        """
        print("=" * 50, flush=True)
        print("[Town State] Starting Town Recovery & Warp Cycle...", flush=True)
        print("=" * 50, flush=True)

        # Check current HP ratio
        hp_ratio = 1.0
        if self.detector and frame is not None:
            hp_ratio = self.detector.get_player_hp_ratio(frame)

        # 1. ONLY heal at Heart NPC if HP is NOT full (< 0.88)
        if hp_ratio < 0.88:
            print(f"[Town State] Character HP is {hp_ratio*100:.1f}% -> Visiting Heart NPC to heal...", flush=True)
            self.heal_at_heart_npc(frame=frame)
        else:
            print(f"[Town State] Character HP is already full ({hp_ratio*100:.1f}%) -> Skipping Heart NPC and heading directly to Teleport Crystal!", flush=True)

        # Capture updated frame if possible
        fresh_frame = self.controller.capture_frame() if hasattr(self.controller, "capture_frame") else frame

        # 2. Interact with Teleport Crystal
        self.interact_teleport_crystal(frame=fresh_frame)

        # Capture updated frame if possible
        fresh_frame_warp = self.controller.capture_frame() if hasattr(self.controller, "capture_frame") else fresh_frame

        # 3. Warp to farming zone
        self.execute_warp_to_zone(frame=fresh_frame_warp)

        print("[Town State] Town recovery cycle completed successfully!", flush=True)
        return True
