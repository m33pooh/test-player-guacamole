import base64
import json
import os
from typing import Dict, Any, Optional
import cv2
import numpy as np
import requests


class VLMInspector:
    """
    Vision-Language Model (VLM) Inspector.
    Invoked for slow-path scene understanding:
    - Lie detector / anti-bot verification dialogs
    - Game Master (GM) chat messages
    - Unexpected room transitions (e.g. White Room, Captcha)
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.endpoint = endpoint or os.getenv("UNSLOTH_ENDPOINT", "http://127.0.0.1:8888/v1")
        self.model = model or os.getenv("UNSLOTH_MODEL", "unsloth/Qwen3-VL-4B-Instruct-GGUF")
        self.api_key = api_key or os.getenv("UNSLOTH_API_KEY", "")

    def encode_image(self, frame: np.ndarray, quality: int = 75) -> str:
        """
        Converts OpenCV frame to base64 JPEG string.
        """
        success, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if not success:
            return ""
        return base64.b64encode(buffer).decode("utf-8")

    def inspect_scene(self, frame: np.ndarray, prompt: Optional[str] = None) -> Dict[str, Any]:
        """
        Sends frame to VLM to inspect security alerts or dialogs.
        """
        b64_img = self.encode_image(frame)
        if not b64_img:
            return {"status": "error", "message": "Failed to encode frame"}

        query_prompt = prompt or (
            "Analyze this MapleStory screenshot. Check for:\n"
            "1. Is there an anti-bot or lie detector captcha dialog open?\n"
            "2. Is the character in a GM verification room or white room?\n"
            "3. Are there GM or player chat messages requiring an urgent response?\n"
            "Respond in JSON format with keys: captcha_detected (bool), white_room (bool), chat_alert (bool), summary (str)."
        )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}" if self.api_key else "",
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": query_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}},
                    ],
                }
            ],
            "max_tokens": 250,
            "temperature": 0.1,
        }

        try:
            url = f"{self.endpoint.rstrip('/')}/chat/completions"
            resp = requests.post(url, headers=headers, json=payload, timeout=6.0)
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                # Parse JSON if possible
                try:
                    # Strip markdown blocks if present
                    clean = content.strip()
                    if clean.startswith("```json"):
                        clean = clean[7:]
                    if clean.endswith("```"):
                        clean = clean[:-3]
                    return json.loads(clean.strip())
                except Exception:
                    return {"status": "ok", "raw_response": content}
            else:
                return {"status": "error", "code": resp.status_code, "text": resp.text[:200]}
        except Exception as e:
            return {"status": "unavailable", "error": str(e)}
