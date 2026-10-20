import os
import sys
import cv2
import numpy as np

TEMPLATE_DIR = "data/templates/monsters"


def crop_and_save_template(
    image_path: str,
    x: int,
    y: int,
    width: int,
    height: int,
    mob_name: str,
    angle: str = "front",
    zone: str = "stormreef_isle",
):
    """
    Crops a sub-region from an existing screenshot and saves it directly to the template bank.
    Usage Example:
        crop_and_save_template("data/live_debug_screen.jpg", 400, 300, 80, 80, "crab", "side")
    """
    if not os.path.exists(image_path):
        print(f"[Error] Image file not found: {image_path}")
        return False

    img = cv2.imread(image_path)
    if img is None:
        print(f"[Error] Failed to read image: {image_path}")
        return False

    h, w = img.shape[:2]
    x1 = max(0, min(w - 1, x))
    y1 = max(0, min(h - 1, y))
    x2 = max(x1 + 1, min(w, x + width))
    y2 = max(y1 + 1, min(h, y + height))

    crop = img[y1:y2, x1:x2]
    if crop.size == 0:
        print("[Error] Crop region is empty.")
        return False

    zone_dir = os.path.join(TEMPLATE_DIR, zone)
    os.makedirs(zone_dir, exist_ok=True)
    filename = f"{mob_name}_{angle}.png"
    out_path = os.path.join(zone_dir, filename)

    cv2.imwrite(out_path, crop)
    print(f"[Success] Monster template saved: {out_path} ({crop.shape[1]}x{crop.shape[0]} px)")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 7:
        print("Usage: python -m app.vision.crop_tool <image_path> <x> <y> <w> <h> <mob_name> [angle] [zone]")
        print("Example: python -m app.vision.crop_tool data/live_debug_screen.jpg 500 350 70 70 crab front stormreef_isle")
    else:
        img_p = sys.argv[1]
        x = int(sys.argv[2])
        y = int(sys.argv[3])
        w = int(sys.argv[4])
        h = int(sys.argv[5])
        name = sys.argv[6]
        angle = sys.argv[7] if len(sys.argv) > 7 else "front"
        zone = sys.argv[8] if len(sys.argv) > 8 else "stormreef_isle"
        crop_and_save_template(img_p, x, y, w, h, name, angle, zone)
