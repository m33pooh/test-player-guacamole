import os
import sys
import time
from typing import Optional

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.controller.controller import ActionController
from app.state_machine.town import TownStateHandler
from app.vision.detector import FastVisionDetector
from config.settings import get_default_config


def main():
    print("=" * 60)
    print(" === Standalone Town Healing & Crystal Test (Playwright Mode) ===")
    print("=" * 60)

    config = get_default_config()

    # 1. Initialize ActionController exactly like main.py
    controller = ActionController(config.controller)
    print(f"[Controller] Initializing ActionController in 'playwright' mode...")
    controller.connect(mode="playwright")

    # 2. Initialize Vision Detector and TownStateHandler
    detector = FastVisionDetector(config.vision)
    town_handler = TownStateHandler(controller=controller, coords=config.coords, detector=detector)

    # 3. Capture initial live screenshot
    print("\n[Step 1] Capturing live town frame from Playwright session...")
    frame = controller.capture_frame()
    if frame is None or frame.size == 0:
        print("[Error] Failed to capture live frame from Playwright browser.")
        return

    h, w = frame.shape[:2]
    print(f"[Resolution] Live Frame Size: {w}x{h}")

    hp_before = detector.get_player_hp_ratio(frame)
    print(f"[Status] Current Player HP Ratio: {hp_before * 100:.1f}%")

    # 4. Execute Town Healing Cycle at Heart NPC
    print("\n[Step 2] Executing Heal Cycle at Heart NPC...")
    town_handler.heal_at_heart_npc(frame=frame)

    # 5. Capture new frame and verify HP
    print("\n[Step 3] Verifying Restored HP...")
    frame_after = controller.capture_frame()
    if frame_after is not None:
        hp_after = detector.get_player_hp_ratio(frame_after)
        print(f"[Status] Updated Player HP Ratio: {hp_after * 100:.1f}%")

    # 6. Execute Teleport Crystal Interaction
    print("\n[Step 4] Executing Teleport Crystal Walk & Open Menu...")
    town_handler.interact_teleport_crystal(frame=frame_after)

    print("\n" + "=" * 60)
    print(" [Success] Standalone Town Healing & Crystal Test Finished!")
    print("=" * 60)


if __name__ == "__main__":
    main()
