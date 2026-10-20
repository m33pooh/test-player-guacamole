import time
import sys
import ctypes

# Try importing pyautogui, fallback to native ctypes for Windows
try:
    import pyautogui
    HAS_PYAUTOGUI = True
    pyautogui.PAUSE = 0.1
    pyautogui.FAILSAFE = True
except ImportError:
    HAS_PYAUTOGUI = False

# Native Windows API Key Mapping
VK_KEYS = {
    '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34, '5': 0x35,
    '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39, '0': 0x30,
    'q': 0x51, 'w': 0x57, 'e': 0x45, 'r': 0x52, 't': 0x54, 'y': 0x59
}

def win_press_key(char):
    if HAS_PYAUTOGUI:
        pyautogui.press(char)
    else:
        vk = VK_KEYS.get(char.lower())
        if vk:
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0) # KEYEVENTF_KEYUP

def win_click(x, y):
    if HAS_PYAUTOGUI:
        pyautogui.click(x, y)
    else:
        ctypes.windll.user32.SetCursorPos(x, y)
        ctypes.windll.user32.mouse_event(2, 0, 0, 0, 0) # MOUSEEVENTF_LEFTDOWN
        time.sleep(0.05)
        ctypes.windll.user32.mouse_event(4, 0, 0, 0, 0) # MOUSEEVENTF_LEFTUP

def win_move_mouse(x, y):
    if HAS_PYAUTOGUI:
        pyautogui.moveTo(x, y)
    else:
        ctypes.windll.user32.SetCursorPos(x, y)

from monster_vision import MonsterDetector
from memory_engine import MemoryEngine

class AutoGrindBot:
    """
    Dual-Loop Automated MMORPG Farming Engine
    - Fast Loop: High-frequency combat skill rotation (30-60 Hz) targeting main viewport
    - Slow Loop: Minimap navigation & monster vision scanning
    """
    def __init__(self):
        self.running = False
        self.last_slow_loop_time = 0.0
        self.detector = MonsterDetector()
        self.memory = MemoryEngine()
        # Main viewport center target for skill mouse clicks (prevents clicking minimap UI during attacks)
        self.skill_target_coords = (960, 480)

    def fast_loop_attack(self):
        """Fast Loop: Executes Movement Approach followed by Combat Attack Combo"""
        tx, ty = self.skill_target_coords
        
        # STEP 1: MOVEMENT STEP (ขยับเข้าหามอนสเตอร์)
        print(f"[Movement Step] Moving character towards ({tx}, {ty})...")
        win_move_mouse(tx, ty)
        win_click(tx, ty)
        time.sleep(0.3)

        # STEP 2: COMBAT ATTACK STEP (โจมตีมอนสเตอร์)
        print("[Attack Step] Executing targeted skill combo...")

        # 1. Buff Maintenance
        win_press_key('6')
        time.sleep(0.05)

        # 2. Skill 3 (Pull mobs in circle at mouse) -> Skill Y -> Skill T (AoE around self)
        print("[Fast Loop] Executing Pull & Self-AoE Combo (3 -> Y -> T)")
        win_press_key('3')
        time.sleep(0.1)
        win_click(tx, ty)
        time.sleep(0.05)
        win_press_key('y')
        time.sleep(0.05)
        win_press_key('t')
        time.sleep(0.1)

        # 3. Skill 1 (AoE targeting at mouse)
        print("[Fast Loop] Skill 1 (AoE at mouse)")
        win_press_key('1')
        win_click(tx, ty)
        time.sleep(0.05)

        # 4. Skill 2 & Q (Single Target at mouse)
        print("[Fast Loop] Skill 2 & Q (Single Target at mouse)")
        win_press_key('2')
        time.sleep(0.05)
        win_press_key('q')
        time.sleep(0.05)

        # 5. Skill 4 (Dodge Jump)
        print("[Fast Loop] Skill 4 (Dodge Jump)")
        win_press_key('4')
        time.sleep(0.05)

    def slow_loop_search_mobs(self):
        """Slow Loop: Uses Computer Vision to detect monsters on minimap & main screen"""
        print("[Slow Loop - Computer Vision Engine] Scanning screen for monsters...")
        target_coords, target_type = self.detector.get_best_target()
        
        if target_type == "MAIN_SCREEN_MOB":
            # Target is an enemy HP bar on screen -> set as skill target
            self.skill_target_coords = target_coords
            win_click(target_coords[0], target_coords[1])
        else:
            # Target is a minimap radar dot -> click minimap ONCE for movement, reset skill target to center viewport
            print(f"[Slow Loop Navigation] Moving character via minimap click at {target_coords}")
            win_click(target_coords[0], target_coords[1])
            self.skill_target_coords = (960, 480) # Reset skill aim to viewport center
            
        time.sleep(1.5)

    def run_continuous(self, duration_seconds=60):
        """Main Infinite Loop executing Dual-Loop Architecture"""
        print("=== Starting Auto-Grind Loop (Move mouse to top-left corner to STOP) ===")
        self.running = True
        start_time = time.time()

        try:
            while self.running:
                current_time = time.time()
                if current_time - start_time > duration_seconds:
                    print("[Auto-Grind] Specified duration reached.")
                    break

                # 1. Fast Loop (Always active)
                self.fast_loop_attack()

                # 2. Slow Loop (Triggers every 10 seconds to find mobs)
                if current_time - self.last_slow_loop_time > 10.0:
                    self.slow_loop_search_mobs()
                    self.last_slow_loop_time = current_time

                time.sleep(0.2)
        except pyautogui.FailSafeException:
            print("[Auto-Grind] FailSafe triggered by user (Mouse in corner). Stopping bot.")
        except KeyboardInterrupt:
            print("[Auto-Grind] Interrupted by user. Stopping bot.")
        finally:
            self.running = False
            print("=== Auto-Grind Bot Stopped ===")

if __name__ == "__main__":
    bot = AutoGrindBot()
    # Run a test loop for 30 seconds
    bot.run_continuous(duration_seconds=30)
