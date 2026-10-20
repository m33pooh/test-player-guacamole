import os
import time
import sys
import numpy as np
import cv2

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from monster_vision import MonsterDetector
from memory_engine import MemoryEngine
from qwen_vlm_agent import QwenVLStrategicBrain
from target_tracker import TargetMemoryTracker
from bot_web_server import TelemetryHub, start_dashboard_in_background
import base64

GUACAMOLE_URL = os.getenv("GUACAMOLE_URL", "http://localhost:60289/guacamole/#/client/UkRQIENvbm5lY3Rpb24AYwBkZWZhdWx0")


class BotWorkflowState:
    DEAD_RECOVERY = "DEAD_RECOVERY"
    TOWN_REFILL = "TOWN_REFILL"
    TOWN_OPEN_MAP = "TOWN_OPEN_MAP"
    TOWN_WARP = "TOWN_WARP"
    FIELD_NAVIGATE = "FIELD_NAVIGATE"
    FIELD_COMBAT = "FIELD_COMBAT"


def annotate_game_frame(frame, state, hp_ratio, in_town, enemies, target_info, heart_pos=None, nav_info=None):
    """
    Renders visual bounding boxes, target crosshairs, and Cyberpunk telemetry HUD directly onto the frame.
    """
    if frame is None or not isinstance(frame, np.ndarray):
        return frame

    vis = frame.copy()
    fh, fw, _ = vis.shape

    # 1. Top-Left Player HP Bar Outline
    x1, y1 = int(fw * 0.008), int(fh * 0.055)
    x2, y2 = int(fw * 0.125), int(fh * 0.085)
    hp_color = (0, 255, 136) if hp_ratio > 0.35 else (0, 50, 255)
    cv2.rectangle(vis, (x1, y1), (x2, y2), hp_color, 2)
    cv2.putText(vis, f"HP: {int(hp_ratio*100)}%", (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, hp_color, 2)

    # 2. Detected Monster HP Bars
    if enemies:
        for idx, (ex, ey) in enumerate(enemies):
            cv2.rectangle(vis, (ex - 22, ey - 8), (ex + 22, ey + 8), (0, 0, 255), 2)
            cv2.putText(vis, f"MOB #{idx+1}", (ex - 22, ey - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 100, 255), 1)

    # 3. Active Target Crosshair & Lock Ring
    if target_info and target_info.get("x") and target_info.get("y"):
        tx, ty = target_info["x"], target_info["y"]
        # Scale to frame coords if in CSS
        if tx < 1800 and fw > 2000:
            scale_x = fw / 1707.0
            scale_y = fh / 932.0
            f_tx, f_ty = int(tx * scale_x), int(ty * scale_y)
        else:
            f_tx, f_ty = tx, ty

        cv2.circle(vis, (f_tx, f_ty), 24, (0, 240, 255), 2)
        cv2.circle(vis, (f_tx, f_ty), 4, (0, 240, 255), -1)
        cv2.line(vis, (f_tx - 32, f_ty), (f_tx + 32, f_ty), (0, 240, 255), 1)
        cv2.line(vis, (f_tx, f_ty - 32), (f_tx, f_ty + 32), (0, 240, 255), 1)
        cv2.putText(vis, "TARGET LOCK", (f_tx - 40, f_ty + 38), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 240, 255), 1)

    # 4. Heart NPC Marker in Town
    if in_town and heart_pos:
        hx, hy = heart_pos
        cv2.circle(vis, (hx, hy), 28, (255, 0, 255), 2)
        cv2.putText(vis, "HEART NPC (HEALER)", (hx - 60, hy - 34), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 2)

    # 5. Minimap Radar Box (Top Right)
    mm_x1, mm_y1 = int(fw * 0.82), int(fh * 0.01)
    mm_x2, mm_y2 = int(fw * 0.99), int(fh * 0.20)
    cv2.rectangle(vis, (mm_x1, mm_y1), (mm_x2, mm_y2), (0, 240, 255), 1)
    cv2.putText(vis, "MINIMAP RADAR", (mm_x1 + 6, mm_y1 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 240, 255), 1)

    # 6. Bottom Cyberpunk HUD Banner
    hud_h = 42
    overlay = vis.copy()
    cv2.rectangle(overlay, (0, fh - hud_h), (fw, fh), (10, 14, 22), -1)
    cv2.addWeighted(overlay, 0.82, vis, 0.18, 0, vis)
    cv2.line(vis, (0, fh - hud_h), (fw, fh - hud_h), (0, 240, 255), 1)

    hud_text = f"STATE: [{state}] | HP: {int(hp_ratio*100)}% | ZONE: {'TOWN' if in_town else 'FIELD'} | MOBS: {len(enemies) if enemies else 0}"
    cv2.putText(vis, hud_text, (20, fh - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    return vis


class MinimapNavigator:
    """
    Dedicated Minimap Radar Navigation Module:
    - Locates player white arrow and closest monster red dots on the minimap.
    - Clicks directly on the minimap red dot to use the game's built-in 3D auto-pathfinder.
    """
    def __init__(self, detector: MonsterDetector):
        self.detector = detector
        self.step_count = 0

    def rotate_camera(self, page, direction="right", angle_step=160):
        try:
            cx, cy = 853, 466
            dx = angle_step if direction == "right" else -angle_step
            print(f"[Minimap Navigator] Rotating camera ({direction})...", flush=True)
            page.mouse.move(cx, cy)
            page.mouse.down(button="right")
            time.sleep(0.08)
            page.mouse.move(cx + dx, cy, steps=6)
            time.sleep(0.08)
            page.mouse.up(button="right")
            time.sleep(0.15)
            key = "ArrowRight" if direction == "right" else "ArrowLeft"
            page.keyboard.press(key, delay=100)
        except Exception as e:
            print(f"[Minimap Navigator Warning] Camera rotation error: {e}", flush=True)

    def navigate_to_nearest_monster(self, page, frame):
        self.step_count += 1
        nav_info = self.detector.get_minimap_navigation_vector(frame)

        if not nav_info:
            print("[Minimap Navigator] No monster red dots visible on minimap. Rotating camera to scan...", flush=True)
            self.rotate_camera(page, direction="right" if (self.step_count % 2 == 0) else "left")
            return False

        target_dot = nav_info["target_dot"]
        total_mobs = nav_info["total_mobs"]
        current_distance = nav_info["distance"]

        viewport = page.viewport_size or {"width": 1707, "height": 932}
        vw, vh = viewport["width"], viewport["height"]
        fh, fw, _ = frame.shape

        map_origin_x = int(fw * 0.82)
        map_origin_y = int(fh * 0.01)
        global_dot_x = map_origin_x + target_dot[0]
        global_dot_y = map_origin_y + target_dot[1]

        click_x = int(global_dot_x * (vw / fw))
        click_y = int(global_dot_y * (vh / fh))

        print(f"[Minimap Navigator] Moving towards monster: Clicking Minimap Red Dot at ({click_x}, {click_y}) | Distance: {current_distance:.0f}px | Remaining Mobs: {total_mobs}", flush=True)
        page.mouse.click(click_x, click_y)
        time.sleep(1.8)
        return True


class CombatFarmingEngine:
    """
    Dedicated Field Combat Module:
    - Advances forward towards monster targets without retreating.
    - Rotates Gunslinger skills: Skill 3 (Pull), Skill 1 (AoE Blast), direct attack skills (Q, 2, E, T, Y, R).
    - Manages potion (5) and survival buff (6).
    """
    def __init__(self):
        self.last_skill_3_time = 0
        self.last_skill_4_time = 0

    def manage_survival(self, page, hp_ratio, current_time):
        if hp_ratio < 0.60:
            print(f"[Health Management] HP at {hp_ratio*100:.0f}%, using potion (5)...", flush=True)
            page.keyboard.press("5", delay=25)

    def execute_combat_cycle(self, page, target_info):
        tx, ty = target_info["x"], target_info["y"]
        px, py = 853, 466
        now = time.time()

        dx = tx - px
        dy = ty - py
        dist = max(1.0, (dx**2 + dy**2)**0.5)

        # 1. Forward Engagement (Advance directly toward monster if further than 220px)
        if dist > 220:
            approach_dist = dist - 180
            ax = int(px + (dx / dist) * approach_dist)
            ay = int(py + (dy / dist) * approach_dist)
            ax = max(160, min(1380, ax))
            ay = max(200, min(760, ay))
            print(f"[Combat Engine] Advancing towards target: Ground Click at ({ax}, {ay})...", flush=True)
            page.mouse.click(ax, ay)
            time.sleep(0.20)

        # 2. Buff (6) and Potion (5)
        page.keyboard.press("6", delay=25)
        page.keyboard.press("5", delay=25)

        # 3. Calculate AoE placement towards monster
        aoe_dist = min(dist * 0.40, 140)
        aoe_x = int(px + (dx / dist) * aoe_dist)
        aoe_y = int(py + (dy / dist) * aoe_dist)

        # 4. Crowd Control Pull (3)
        if (now - self.last_skill_3_time) > 4.5:
            print(f"[Combat Engine] Skill 3 Vacuum Pull at ({aoe_x}, {aoe_y})...", flush=True)
            page.mouse.move(aoe_x, aoe_y)
            page.keyboard.press("3", delay=30)
            page.mouse.click(aoe_x, aoe_y)
            self.last_skill_3_time = now

        # 5. Stacking AoE Blast (1)
        page.mouse.move(aoe_x, aoe_y)
        page.keyboard.press("1", delay=30)
        page.mouse.click(aoe_x, aoe_y)

        # 6. Direct Attack Skills (Q, 2, E, T, Y, R)
        page.mouse.move(tx, ty)
        for key in ["q", "2", "e", "t", "y", "r"]:
            page.keyboard.press(key, delay=25)
            page.mouse.click(tx, ty)

        # 7. Follow-up AoE (1)
        page.mouse.move(aoe_x, aoe_y)
        page.keyboard.press("1", delay=25)
        page.mouse.click(aoe_x, aoe_y)


class PlaywrightGuacamoleBot:
    """
    Finite State Machine (FSM) Workflow Engine for MMORPG Automation
    Strictly isolates Town Workflow from Field Navigation and Combat Workflow.
    """
    def __init__(self, target_url=GUACAMOLE_URL):
        self.target_url = target_url
        self.detector = MonsterDetector()
        self.memory = MemoryEngine()
        self.qwen_brain = QwenVLStrategicBrain()
        self.target_tracker = TargetMemoryTracker()
        self.navigator = MinimapNavigator(self.detector)
        self.combat_engine = CombatFarmingEngine()
        self.state = BotWorkflowState.TOWN_REFILL
        self.hub = TelemetryHub()
        self.last_snapshot_time = 0.0

    def capture_frame(self, page):
        try:
            screenshot_bytes = page.screenshot(type="jpeg", quality=65, timeout=1500)
            nparr = np.frombuffer(screenshot_bytes, np.uint8)
            return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        except Exception:
            return self.detector.capture_screenshot()

    def run_browser_agent(self, duration_seconds=0):
        if not HAS_PLAYWRIGHT:
            print("[Error] Playwright is not installed. Please run: pip install playwright", flush=True)
            return

        # Start Web Dashboard Server
        try:
            start_dashboard_in_background(port=8888)
        except Exception as srv_err:
            print(f"[Dashboard Server Notice] {srv_err}", flush=True)

        print(f"=== Connecting Playwright to Existing Browser (CDP Port 9222) ===", flush=True)
        print(f"Target URL: {self.target_url}", flush=True)
        print(f"Live Web Dashboard available at: http://localhost:8888", flush=True)

        with sync_playwright() as p:
            try:
                try:
                    browser = p.chromium.connect_over_cdp("http://localhost:9222", timeout=3000)
                    context = browser.contexts[0]
                    page = None
                    for p_item in context.pages:
                        if "guacamole" in p_item.url:
                            page = p_item
                            break

                    if not page:
                        print("[Playwright Bot] Guacamole tab not found in CDP browser, opening target tab...", flush=True)
                        page = context.new_page()
                        page.goto(self.target_url)
                    else:
                        print(f"[Playwright Bot] Attached to existing Guacamole tab: {page.url}", flush=True)
                except Exception as cdp_err:
                    print(f"[Playwright Bot] CDP connection unavailable ({cdp_err}). Launching standalone browser...", flush=True)
                    browser = p.chromium.launch(headless=False, args=["--start-maximized"])
                    context = browser.new_context(no_viewport=True)
                    page = context.new_page()
                    page.goto(self.target_url, timeout=10000)

                page.bring_to_front()
                time.sleep(0.5)

                viewport = page.viewport_size or {"width": 1707, "height": 932}
                vw, vh = viewport["width"], viewport["height"]

                # Initial State Detection
                init_frame = self.capture_frame(page)
                if self.detector.check_player_dead(init_frame):
                    self.state = BotWorkflowState.DEAD_RECOVERY
                elif self.detector.check_is_in_town(init_frame):
                    self.state = BotWorkflowState.TOWN_REFILL
                else:
                    self.state = BotWorkflowState.FIELD_NAVIGATE

                print(f"=== Workflow State Machine Initialized: Starting in [{self.state}] ===", flush=True)
                self.hub.record_action("STATE_CHANGE", f"Bot initialized in [{self.state}]")

                start_time = time.time()

                while True:
                    if duration_seconds and duration_seconds > 0:
                        if time.time() - start_time >= duration_seconds:
                            print(f"[Playwright Bot] Target duration ({duration_seconds}s) reached.", flush=True)
                            break

                    frame = self.capture_frame(page)
                    current_time = time.time()

                    # Telemetry calculations
                    hp_ratio = self.detector.get_player_hp_ratio(frame)
                    in_town = self.detector.check_is_in_town(frame)
                    heart_pos = self.detector.find_heart_npc(frame) if in_town else None
                    enemies = self.detector.find_onscreen_enemies_hsv(frame) if not in_town else []
                    
                    target_info = None
                    if not in_town:
                        target_info = self.target_tracker.get_current_target()

                    # Render Visual Overlays & Stream to Web Dashboard
                    annotated_frame = annotate_game_frame(
                        frame, self.state, hp_ratio, in_town, enemies, target_info, heart_pos=heart_pos
                    )
                    self.hub.update_frame(frame, annotated_frame)
                    self.hub.update_telemetry(self.state, hp_ratio, in_town, enemies, target_info)

                    # Periodic Snapshot for Scan History Audit
                    if current_time - self.last_snapshot_time > 2.5:
                        try:
                            # Generate small thumbnail (320x180)
                            thumb = cv2.resize(annotated_frame, (320, 180))
                            _, thumb_jpg = cv2.imencode(".jpg", thumb, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
                            thumb_b64 = base64.b64encode(thumb_jpg).decode("utf-8")
                            
                            detections_summary = {
                                "hp_percent": int(hp_ratio * 100),
                                "in_town": in_town,
                                "monsters_found": len(enemies),
                                "target": target_info,
                                "heart_npc": heart_pos
                            }
                            self.hub.record_scan_snapshot(thumb_b64, self.state, detections_summary, self.hub.current_action)
                            self.last_snapshot_time = current_time
                        except Exception:
                            pass

                    # Global Safety Check 1: Disconnection
                    if self.detector.check_disconnection(frame):
                        print("[Workflow] Guacamole disconnected! Clicking Reconnect...", flush=True)
                        self.hub.record_action("DISCONNECT", "Guacamole session disconnected! Clicking Reconnect button...")
                        try:
                            page.mouse.click(473, 524)
                            time.sleep(2.0)
                        except Exception:
                            pass
                        continue

                    # Global Safety Check 2: Death Detection
                    if self.detector.check_player_dead(frame) and self.state != BotWorkflowState.DEAD_RECOVERY:
                        print(f"[Workflow] Player death detected! Transitioning -> [{BotWorkflowState.DEAD_RECOVERY}]", flush=True)
                        self.hub.record_action("DEATH", f"Player died! HP: {hp_ratio*100:.0f}% -> Switching to DEAD_RECOVERY")
                        self.state = BotWorkflowState.DEAD_RECOVERY

                    # -------------------------------------------------------------
                    # STATE 1: DEAD_RECOVERY (คลิกปุ่มชุบ Respawn In Town)
                    # -------------------------------------------------------------
                    if self.state == BotWorkflowState.DEAD_RECOVERY:
                        fh, fw, _ = frame.shape
                        btn_pos = self.detector.get_revive_button_coords(frame)
                        if btn_pos:
                            rx = int(btn_pos[0] * (vw / fw))
                            ry = int(btn_pos[1] * (vh / fh))
                        else:
                            rx, ry = 853, 678

                        print(f"[State: DEAD_RECOVERY] Clicking 'Respawn In Town' at ({rx}, {ry})...", flush=True)
                        self.hub.record_action("REVIVE", f"Clicking 'Respawn In Town' button at ({rx}, {ry})")
                        page.mouse.click(rx, ry)
                        time.sleep(0.3)
                        page.keyboard.press("Enter")
                        page.keyboard.press("Space")
                        
                        print("[State: DEAD_RECOVERY] Respawned! Waiting 4s for town load...", flush=True)
                        time.sleep(4.0)
                        
                        print(f"[Workflow Transition] [{BotWorkflowState.DEAD_RECOVERY}] -> [{BotWorkflowState.TOWN_REFILL}]", flush=True)
                        self.hub.record_action("STATE_CHANGE", f"Respawned in Town! [{BotWorkflowState.DEAD_RECOVERY}] -> [{BotWorkflowState.TOWN_REFILL}]")
                        self.state = BotWorkflowState.TOWN_REFILL
                        continue

                    # -------------------------------------------------------------
                    # STATE 2: TOWN_REFILL (เติมเลือดที่ Heart NPC)
                    # -------------------------------------------------------------
                    elif self.state == BotWorkflowState.TOWN_REFILL:
                        print("[State: TOWN_REFILL] Refilling HP & Potions at Heart NPC...", flush=True)
                        fh, fw, _ = frame.shape
                        heart_pos = self.detector.find_heart_npc(frame)
                        if heart_pos:
                            hx = int(heart_pos[0] * (vw / fw))
                            hy = int(heart_pos[1] * (vh / fh))
                        else:
                            hx, hy = 1100, 609

                        print(f"[State: TOWN_REFILL] Talking to Heart NPC at ({hx}, {hy})...", flush=True)
                        self.hub.record_action("HEAL", f"Interacting with Heart NPC (Healer) at ({hx}, {hy}) to refill HP/potions")
                        page.mouse.click(hx, hy)
                        time.sleep(0.8)
                        page.mouse.dblclick(hx, hy)
                        time.sleep(0.4)
                        page.keyboard.press("Space", delay=100)
                        time.sleep(0.5)
                        
                        print(f"[Workflow Transition] [{BotWorkflowState.TOWN_REFILL}] -> [{BotWorkflowState.TOWN_OPEN_MAP}]", flush=True)
                        self.hub.record_action("STATE_CHANGE", f"HP refilled! [{BotWorkflowState.TOWN_REFILL}] -> [{BotWorkflowState.TOWN_OPEN_MAP}]")
                        self.state = BotWorkflowState.TOWN_OPEN_MAP
                        continue

                    # -------------------------------------------------------------
                    # STATE 3: TOWN_OPEN_MAP (เปิด World Map ผ่าน Teleport Crystal)
                    # -------------------------------------------------------------
                    elif self.state == BotWorkflowState.TOWN_OPEN_MAP:
                        print("[State: TOWN_OPEN_MAP] Interacting with Teleport Crystal to open World Map...", flush=True)
                        self.hub.record_action("MAP_OPEN", "Walking & interacting with Teleport Crystal to open World Map")
                        page.mouse.click(1430, 200)
                        time.sleep(0.8)
                        page.mouse.dblclick(1430, 200)
                        time.sleep(0.3)
                        page.keyboard.press("f")
                        time.sleep(1.0)
                        
                        print(f"[Workflow Transition] [{BotWorkflowState.TOWN_OPEN_MAP}] -> [{BotWorkflowState.TOWN_WARP}]", flush=True)
                        self.hub.record_action("STATE_CHANGE", f"World Map opened! [{BotWorkflowState.TOWN_OPEN_MAP}] -> [{BotWorkflowState.TOWN_WARP}]")
                        self.state = BotWorkflowState.TOWN_WARP
                        continue

                    # -------------------------------------------------------------
                    # STATE 4: TOWN_WARP (เลือกเกาะ Stormreef Isle แล้ววาปไปฟาร์ม)
                    # -------------------------------------------------------------
                    elif self.state == BotWorkflowState.TOWN_WARP:
                        print("[State: TOWN_WARP] Selecting Stormreef Isle (Lv 61-65) and warping...", flush=True)
                        self.hub.record_action("WARP_SELECT", "Selecting Stormreef Isle (Lv 61-65) on World Map and clicking Warp")
                        page.mouse.click(455, 430)
                        time.sleep(0.3)
                        page.mouse.dblclick(455, 430)
                        time.sleep(0.3)
                        page.mouse.click(1620, 915)
                        
                        # Wait and verify map transition
                        print("[State: TOWN_WARP] Waiting for map loading and verifying arrival in field...", flush=True)
                        self.hub.record_action("WARP_WAIT", "Warping: Waiting for field map loading screen...")
                        time.sleep(3.0)
                        for attempt in range(8):
                            check_frame = self.capture_frame(page)
                            if not self.detector.check_is_in_town(check_frame):
                                print(f"[State: TOWN_WARP] Map transition confirmed! Arrived in hunting field (attempt {attempt+1}).", flush=True)
                                break
                            time.sleep(1.0)

                        # Proactive buff and potion upon arrival
                        print("[State: TOWN_WARP] Arrived in field. Buffing Gunslinger (6)...", flush=True)
                        self.hub.record_action("BUFF", "Arrived at Stormreef Isle! Casting Gunslinger Buff (6) & Potion (5)")
                        page.keyboard.press("6", delay=50)
                        page.keyboard.press("5", delay=50)
                        time.sleep(0.5)

                        print(f"[Workflow Transition] Map crossed! [{BotWorkflowState.TOWN_WARP}] -> [{BotWorkflowState.FIELD_COMBAT}]", flush=True)
                        self.hub.record_action("STATE_CHANGE", f"Map crossed! [{BotWorkflowState.TOWN_WARP}] -> [{BotWorkflowState.FIELD_COMBAT}]")
                        self.state = BotWorkflowState.FIELD_COMBAT
                        continue

                    # -------------------------------------------------------------
                    # STATE 5: FIELD_NAVIGATE (เดินตามจุดแดงบน Minimap)
                    # -------------------------------------------------------------
                    elif self.state == BotWorkflowState.FIELD_NAVIGATE:
                        enemies = self.detector.find_onscreen_enemies_hsv(frame)
                        if enemies:
                            print(f"[Workflow Transition] Monster HP bar detected onscreen! [{BotWorkflowState.FIELD_NAVIGATE}] -> [{BotWorkflowState.FIELD_COMBAT}]", flush=True)
                            self.hub.record_action("STATE_CHANGE", f"Monster HP bar visible! [{BotWorkflowState.FIELD_NAVIGATE}] -> [{BotWorkflowState.FIELD_COMBAT}]")
                            self.state = BotWorkflowState.FIELD_COMBAT
                            continue

                        print("[State: FIELD_NAVIGATE] Following red dot on minimap...", flush=True)
                        self.hub.record_action("NAVIGATE", "Following monster red dot on Minimap Radar...")
                        self.navigator.navigate_to_nearest_monster(page, frame)

                    # -------------------------------------------------------------
                    # STATE 6: FIELD_COMBAT (คอมโบสกิลโจมตีมอนสเตอร์)
                    # -------------------------------------------------------------
                    elif self.state == BotWorkflowState.FIELD_COMBAT:
                        hp_ratio = self.detector.get_player_hp_ratio(frame)
                        self.combat_engine.manage_survival(page, hp_ratio, current_time)

                        enemies = self.detector.find_onscreen_enemies_hsv(frame)
                        in_active_combat = self.detector.check_top_target_bar(frame)

                        target_info = self.target_tracker.update_or_acquire_target(enemies, player_pos=(853, 466))
                        if not target_info and in_active_combat:
                            target_info = {"x": 853, "y": 466, "type": "active_combat_lock"}

                        if target_info:
                            cx, cy = target_info["x"], target_info["y"]
                            print(f"[State: FIELD_COMBAT] Engaging monster at ({cx}, {cy})...", flush=True)
                            self.hub.record_action("COMBAT", f"Engaging monster at ({cx}, {cy}) | Combo: Pull (3) -> AoE (1) -> Direct (Q,2,E,T,Y,R)")
                            self.combat_engine.execute_combat_cycle(page, target_info)
                        else:
                            print(f"[Workflow Transition] Field cleared! [{BotWorkflowState.FIELD_COMBAT}] -> [{BotWorkflowState.FIELD_NAVIGATE}]", flush=True)
                            self.hub.record_action("STATE_CHANGE", f"Area clear! [{BotWorkflowState.FIELD_COMBAT}] -> [{BotWorkflowState.FIELD_NAVIGATE}]")
                            self.state = BotWorkflowState.FIELD_NAVIGATE

            except KeyboardInterrupt:
                print("[Playwright Bot] Stopped by user (Ctrl+C).", flush=True)
            except Exception as e:
                print(f"[Playwright Bot Error] {e}", flush=True)
            finally:
                print("=== Playwright Bot Session Ended ===", flush=True)


if __name__ == "__main__":
    bot = PlaywrightGuacamoleBot()
    bot.run_browser_agent(duration_seconds=0)
