import time
import cv2
import numpy as np
from playwright.sync_api import sync_playwright

CDP_URL = "http://localhost:9222"
SCREENSHOT_DIR = r"C:\Users\asuslap\.gemini\antigravity-ide\brain\34b520d4-739f-46c1-9db7-e5417a629716"

def run_play_trial():
    print("=== Starting Live MMORPG Gameplay Trial ===")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        page = browser.contexts[0].pages[0]
        print(f"[Playwright] Connected to live page: {page.url}")

        # 1. Apply class buff (Slot 6)
        print("[Action 1] Applying Gunslinger Buff (Key: 6)...")
        page.keyboard.press("6", delay=80)
        time.sleep(0.5)

        # 2. Move & Target closest Monster (Rock Turtle at 340, 555)
        target_x, target_y = 340, 555
        print(f"[Action 2] Moving towards & locking target at ({target_x}, {target_y})...")
        page.mouse.click(target_x, target_y, button="left")
        time.sleep(0.8)

        # 3. Fire Gunslinger Burst Skill Rotation
        print("[Action 3] Executing Gunslinger Skill Combo...")
        combo = ["3", "1", "2", "q", "e", "r"]
        for skill_key in combo:
            print(f" -> Casting Skill '{skill_key.upper()}' at target...")
            page.keyboard.press(skill_key, delay=70)
            time.sleep(0.35)

        # 4. Take Combat Screenshot
        print("[Action 4] Capturing combat action screenshot...")
        shot1 = page.screenshot(type="png")
        with open(f"{SCREENSHOT_DIR}\\combat_trial_step1.png", "wb") as f:
            f.write(shot1)

        time.sleep(1.0)

        # 5. Move to second target (Blue Shark at 205, 475)
        target2_x, target2_y = 205, 475
        print(f"[Action 5] Engaging second monster (Blue Shark) at ({target2_x}, {target2_y})...")
        page.mouse.click(target2_x, target2_y, button="left")
        time.sleep(0.8)

        # Fire second skill rotation
        for skill_key in ["3", "1", "2", "q", "e"]:
            page.keyboard.press(skill_key, delay=70)
            time.sleep(0.35)

        # 6. Take Second Combat Screenshot
        shot2 = page.screenshot(type="png")
        with open(f"{SCREENSHOT_DIR}\\combat_trial_step2.png", "wb") as f:
            f.write(shot2)

        print("=== Gameplay Trial Finished Successfully ===")

if __name__ == "__main__":
    run_play_trial()
