import sys, time, cv2, numpy as np
sys.path.insert(0, 'c:/Users/asuslap/git/testbb')
from maple.app.capture.guacamole_capture import GuacamoleCapture
from maple.app.vision.minimap_tracker import MinimapTracker
from maple.app.vision.mob_detector import MobDetector

cap = GuacamoleCapture()
cap.connect()
page = cap.page
canvas = page.query_selector('canvas')
canvas.click()
time.sleep(0.1)

mob_det = MobDetector()
tracker = MinimapTracker()

def get_target_hp_bar(frame, facing, player_center=(1123, 740)):
    h, w, _ = frame.shape
    y_min = int(h * 0.35)
    roi = frame[y_min:int(h * 0.88), :]
    r = roi[:, :, 2].astype(int)
    g = roi[:, :, 1].astype(int)
    b = roi[:, :, 0].astype(int)
    mask = ((g > 140) & (r < 110) & (b < 90) & ((g - r) > 40)).astype(np.uint8) * 255
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    px, py = player_center
    bars = []
    for c in cnts:
        bx, by, bw, bh = cv2.boundingRect(c)
        abs_x = bx
        abs_y = by + y_min
        dx = abs_x - px
        dy = abs_y - py
        
        # Must be thin horizontal bar, aspect ratio >= 2.5, on current platform level
        if 8 <= bw <= 85 and 3 <= bh <= 6 and (bw / float(bh)) >= 2.2:
            in_front = (dx > 30) if facing == 'right' else (dx < -30)
            if in_front and abs(dx) <= 650 and abs(dy) <= 50:
                hp_pct = min(100.0, max(0.0, (bw / 76.0) * 100.0))
                bars.append({
                    'x': abs_x,
                    'y': abs_y,
                    'width': bw,
                    'height': bh,
                    'hp_percent': round(hp_pct, 1),
                    'dx': dx,
                    'dy': dy,
                })
    bars.sort(key=lambda b: abs(b['dx']))
    return bars[0] if bars else None

print('=== Starting Live Continuous Combat Trial ===')
# Try left and right patrol for up to 3 cycles
for cycle in range(5):
    f = cap.capture_frame()
    m_res = tracker.track(f)
    print(f'Cycle {cycle+1} | Pos: {m_res["player_pos"]}')
    
    for direction in ['right', 'left']:
        dir_key = 'ArrowRight' if direction == 'right' else 'ArrowLeft'
        page.keyboard.press(dir_key)
        time.sleep(0.05)
        
        # Probe shot
        print(f'Probing {direction}...')
        page.keyboard.press('x')
        time.sleep(0.32)
        
        f_probe = cap.capture_frame()
        target = get_target_hp_bar(f_probe, facing=direction)
        
        if target:
            print(f'[Target Locked] Direction: {direction} | Pos: ({target["x"]}, {target["y"]}) | HP: {target["hp_percent"]}% (width: {target["width"]}px)')
            # CONTINUOUS COMBAT LOOP
            for shot in range(1, 9):
                page.keyboard.press('x')
                time.sleep(0.30)
                f_shot = cap.capture_frame()
                cur_bar = get_target_hp_bar(f_shot, facing=direction)
                if not cur_bar:
                    print(f' -> Shot #{shot+1}: Target DEAD! (HP bar disappeared)')
                    print(' -> Looting drops...')
                    for _ in range(3):
                        page.keyboard.press('z')
                        time.sleep(0.12)
                    break
                else:
                    print(f' -> Shot #{shot+1}: Monster Remaining HP = {cur_bar["hp_percent"]}% ({cur_bar["width"]}px)')
        else:
            # Advance slightly
            print(f'No monster in front to {direction}, walking 0.6s...')
            page.keyboard.down(dir_key)
            time.sleep(0.6)
            page.keyboard.up(dir_key)
            time.sleep(0.05)

print('=== Trial Complete ===')
cap.close()
