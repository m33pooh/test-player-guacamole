from playwright.sync_api import sync_playwright
import time
import cv2
import numpy as np

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://localhost:9222", timeout=5000)
    page = None
    for ctx in browser.contexts:
        for pg in ctx.pages:
            if "guacamole" in pg.url:
                page = pg
                break
    page.bring_to_front()
    time.sleep(0.2)

    vp = page.viewport_size
    print(f"Playwright viewport: {vp}")

    ss = page.screenshot(type="png")
    arr = np.frombuffer(ss, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    print(f"Screenshot pixel size: {img.shape[1]}x{img.shape[0]}")

    sx = img.shape[1] / vp["width"]
    sy = img.shape[0] / vp["height"]
    print(f"Scale factors: x={sx:.3f}, y={sy:.3f}")
    print()

    # Minimap bottom-right icons in PIXEL coords -> convert to click coords
    # Minimap icons appear at pixels ~1420-1465, ~195-215 in the 2561x1398 image
    # Click coords = pixel / scale
    for px, py, label in [
        (1426, 202, "book icon (current)"),
        (1463, 202, "reset icon"),
        (1380, 202, "left of icons"),
        (68, 1142, "Map tab in chat bar (1707 scale)"),
        (int(68 * sx), int(761 * sy), "Map tab scaled"),
    ]:
        cx = round(px / sx)
        cy = round(py / sy)
        print(f"  Pixel ({px:4d},{py:3d}) -> Click ({cx:4d},{cy:3d}) | {label}")
