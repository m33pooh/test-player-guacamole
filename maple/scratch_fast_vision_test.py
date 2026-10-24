import sys, time, cv2, numpy as np
sys.path.insert(0, 'c:/Users/asuslap/git/testbb')
from maple.app.capture.guacamole_capture import GuacamoleCapture

cap = GuacamoleCapture()
cap.connect()
page = cap.page
canvas = page.query_selector('canvas')
canvas.click()
time.sleep(0.1)

def check_mobs_on_platform(frame, px=1123, py=700):
    # Strictly our top platform: dx in [-340, -40] (left) and [40, 340] (right)
    # y between 600 and 725
    roi = frame[600:725, :]
    r = roi[:, :, 2].astype(int)
    g = roi[:, :, 1].astype(int)
    b = roi[:, :, 0].astype(int)
    
    # 1. Floating Green HP bar (y between 610 and 670 in frame -> 10 to 70 in roi)
    hp_roi = roi[10:70, :]
    hr = hp_roi[:, :, 2].astype(int)
    hg = hp_roi[:, :, 1].astype(int)
    hb = hp_roi[:, :, 0].astype(int)
    green_mask = (hg > 140) & (hr < 110) & (hb < 90) & ((hg - hr) > 40)
    cnts, _ = cv2.findContours(green_mask.astype(np.uint8)*255, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    left_bars = []
    right_bars = []
    for c in cnts:
        bx, by, bw, bh = cv2.boundingRect(c)
        if 8 <= bw <= 85 and 3 <= bh <= 5 and (bw / float(bh)) >= 2.5:
            dx = bx - px
            if -340 <= dx <= -40:
                left_bars.append({'x': bx, 'width': bw, 'dx': dx})
            elif 40 <= dx <= 340:
                right_bars.append({'x': bx, 'width': bw, 'dx': dx})

    # 2. Monster Sprites:
    # Left crop: x in [px-340, px-40] = [783, 1083]
    # Right crop: x in [px+40, px+340] = [1163, 1463]
    left_crop = roi[:, max(0, px-340):max(0, px-40)]
    right_crop = roi[:, min(frame.shape[1], px+40):min(frame.shape[1], px+340)]
    
    def check_sprite(crop):
        if crop.size == 0:
            return False, 'NONE'
        cr_r = crop[:, :, 2].astype(int)
        cr_g = crop[:, :, 1].astype(int)
        cr_b = crop[:, :, 0].astype(int)
        # Ribbon pig: bright red bandana (at body level y < 90 in roi)
        red_bandana = (cr_r[:90, :] > 165) & (cr_g[:90, :] < 60) & (cr_b[:90, :] < 60)
        if np.sum(red_bandana) >= 20:
            return True, 'Ribbon Pig'
        # Snail orange shell
        orange_shell = (cr_r > 180) & (cr_g > 85) & (cr_g < 165) & (cr_b < 50)
        if np.sum(orange_shell) >= 40:
            return True, 'Snail'
        # Snail / Monster tag: dark translucent box with white text
        dark_box = (cr_r < 60) & (cr_g < 80) & (cr_b < 60)
        cnts_tag, _ = cv2.findContours(dark_box.astype(np.uint8)*255, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts_tag:
            tbx, tby, tbw, tbh = cv2.boundingRect(c)
            if 25 <= tbw <= 80 and 10 <= tbh <= 25 and tby > 40:
                sub = crop[tby:tby+tbh, tbx:tbx+tbw]
                white_cnt = np.sum((sub[:,:,0]>160) & (sub[:,:,1]>160) & (sub[:,:,2]>160))
                if white_cnt >= 12:
                    return True, 'Monster Tag'
        return False, 'NONE'

    l_has_sprite, l_type = check_sprite(left_crop)
    r_has_sprite, r_type = check_sprite(right_crop)
    
    l_active = bool(left_bars) or l_has_sprite
    r_active = bool(right_bars) or r_has_sprite
    
    return {
        'left': {'active': l_active, 'type': l_type, 'bars': left_bars},
        'right': {'active': r_active, 'type': r_type, 'bars': right_bars},
        'any': l_active or r_active
    }

print('=== Live Test: Vision Mob Detection & Stop Shooting ===')
for i in range(15):
    f = cap.capture_frame()
    scan = check_mobs_on_platform(f)
    la = scan["left"]["active"]
    lt = scan["left"]["type"]
    ra = scan["right"]["active"]
    rt = scan["right"]["type"]
    print(f'Tick #{i+1}: Scan = Left({la}, {lt}) | Right({ra}, {rt})')
    
    if not scan['any']:
        print(' -> PLATFORM CLEAR! STOP SHOOTING. Resting and waiting for spawn...')
        time.sleep(0.5)
        continue
        
    # If mob on left:
    if scan['left']['active']:
        print(f' -> Mob spotted on LEFT ({lt})! Fast turning Left...')
        page.keyboard.press('ArrowLeft')
        time.sleep(0.03)
        # Fire 2 continuous shots
        page.keyboard.press('x')
        time.sleep(0.28)
        page.keyboard.press('x')
        time.sleep(0.28)
    elif scan['right']['active']:
        print(f' -> Mob spotted on RIGHT ({rt})! Fast turning Right...')
        page.keyboard.press('ArrowRight')
        time.sleep(0.03)
        # Fire 2 continuous shots
        page.keyboard.press('x')
        time.sleep(0.28)
        page.keyboard.press('x')
        time.sleep(0.28)

cap.close()
print('=== Live Test Complete ===')
