import os
import sys
import json
import numpy as np
import cv2
from qwen_vlm_agent import QwenVLStrategicBrain

def test_qwen_vlm_agent():
    print("=== Testing Unsloth API Strategic Brain (http://127.0.0.1:8888/v1) ===")
    
    # 1. Create a dummy synthetic game screenshot (640x480) with minimap and viewport simulation
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    
    # Draw simulated minimap box (top right)
    cv2.rectangle(img, (480, 10), (630, 160), (50, 50, 50), -1)
    cv2.circle(img, (550, 85), 3, (0, 255, 0), -1) # Player dot
    cv2.circle(img, (530, 65), 2, (0, 0, 255), -1) # Red monster dot 1
    cv2.circle(img, (570, 95), 2, (0, 0, 255), -1) # Red monster dot 2
    
    # Draw simulated player HP bar (top left)
    cv2.rectangle(img, (20, 20), (220, 35), (0, 0, 150), -1)
    cv2.rectangle(img, (20, 20), (180, 35), (0, 255, 0), -1)
    
    # Save temporary test image
    test_img_path = "test_game_screen.jpg"
    cv2.imwrite(test_img_path, img)
    print(f"[Test] Generated synthetic game screenshot: {test_img_path}")
    
    # 2. Instantiate Strategic Brain with Unsloth Studio API Endpoint
    brain = QwenVLStrategicBrain(server_endpoint="http://127.0.0.1:8888/v1")
    
    # 3. Perform analysis
    print("[Test] Sending screenshot to QwenVLStrategicBrain...")
    result = brain.analyze_game_state(test_img_path)
    
    print("\n--- Strategic Brain Output ---")
    print(json.dumps(result, indent=2))
    
    if os.path.exists(test_img_path):
        os.remove(test_img_path)
    
    print("\n[Test] Unsloth API Test Completed Successfully!")

if __name__ == "__main__":
    test_qwen_vlm_agent()
