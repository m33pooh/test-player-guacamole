import base64
import io
import json
import os
import time
from typing import Any, Dict, Optional, Union

import numpy as np
from PIL import Image

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import torch
    from unsloth import FastVisionModel
    HAS_UNSLOTH = True
except Exception:
    HAS_UNSLOTH = False

from config.settings import VLMConfig


class QwenVLStrategicBrain:
    """
    Vision-Language Model (VLM) Strategic Analyzer.
    Supports:
    1. Unsloth Studio / Local API Server (http://127.0.0.1:8888/v1)
    2. Direct Unsloth FastVisionModel (4-bit local CUDA GPU inference)
    3. Standby Rule-based Fallback
    """
    def __init__(self, config: Optional[VLMConfig] = None, backend: str = "auto"):
        self.config = config or VLMConfig()
        self.backend = backend.lower()
        self.server_endpoint = self.config.server_endpoint.rstrip("/")
        self.model_name = self.config.model_name
        self.api_key = self.config.api_key

        self.unsloth_model = None
        self.unsloth_tokenizer = None
        self.active_backend = "none"

        self._initialize_backend()

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _initialize_backend(self):
        # 1. Check server connection (Unsloth API server)
        if self.backend in ["auto", "api", "server", "unsloth_api"]:
            if self._check_server_connection():
                self.active_backend = "server"
                return

        # 2. Check local direct Unsloth model
        if self.backend in ["auto", "unsloth", "local"] and HAS_UNSLOTH:
            self.active_backend = "unsloth_local"
            return

        # 3. Fallback
        self.active_backend = "fallback"

    def _check_server_connection(self) -> bool:
        if not HAS_REQUESTS:
            return False

        candidate_endpoints = [
            self.server_endpoint,
            "http://127.0.0.1:8888/v1",
            "http://localhost:8888/v1",
            "http://localhost:8000/v1",
            "http://localhost:11434/v1",
        ]
        seen = set()
        endpoints = [e for e in candidate_endpoints if not (e in seen or seen.add(e))]

        for ep in endpoints:
            try:
                url = f"{ep}/models"
                resp = requests.get(url, headers=self._get_headers(), timeout=2.0)
                if resp.status_code in [200, 401]:
                    if resp.status_code == 200:
                        data = resp.json().get("data", [])
                        if data:
                            self.model_name = data[0].get("id", self.model_name)
                    self.server_endpoint = ep
                    return True
            except Exception:
                continue
        return False

    def _to_pil_image(self, image_input: Union[Image.Image, np.ndarray, str, bytes]) -> Image.Image:
        if isinstance(image_input, Image.Image):
            return image_input
        if isinstance(image_input, str):
            if os.path.exists(image_input):
                return Image.open(image_input).convert("RGB")
            raise FileNotFoundError(f"Image not found: {image_input}")
        if isinstance(image_input, bytes):
            return Image.open(io.BytesIO(image_input)).convert("RGB")
        if isinstance(image_input, np.ndarray):
            if HAS_OPENCV and len(image_input.shape) == 3 and image_input.shape[2] == 3:
                rgb = cv2.cvtColor(image_input, cv2.COLOR_BGR2RGB)
                return Image.fromarray(rgb)
            return Image.fromarray(image_input)
        raise ValueError(f"Unsupported image format: {type(image_input)}")

    def _encode_image_base64(self, pil_image: Image.Image, max_w: int = 960) -> str:
        w, h = pil_image.size
        if w > max_w:
            pil_image = pil_image.resize((max_w, int(h * max_w / w)), Image.Resampling.LANCZOS)
        buffered = io.BytesIO()
        pil_image.save(buffered, format="JPEG", quality=70)
        return base64.b64encode(buffered.getvalue()).decode("utf-8")

    def _clean_and_parse_json(self, raw_text: str) -> Dict[str, Any]:
        cleaned = raw_text.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0]
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {"raw_text": raw_text, "error": "json_decode_failed"}

    def query_vlm(self, image_input: Any, prompt: str, max_tokens: int = 250) -> Dict[str, Any]:
        """Queries VLM using active backend."""
        pil_img = self._to_pil_image(image_input)

        if self.active_backend == "server":
            return self._call_server_api(pil_img, prompt, max_tokens)
        elif self.active_backend == "unsloth_local":
            return self._call_unsloth_direct(pil_img, prompt, max_tokens)
        else:
            return self._fallback_rule_analysis(image_input)

    def _call_server_api(self, pil_img: Image.Image, prompt: str, max_tokens: int) -> Dict[str, Any]:
        base64_img = self._encode_image_base64(pil_img)
        url = f"{self.server_endpoint}/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"},
                        },
                    ],
                }
            ],
            "max_tokens": max_tokens,
            "temperature": self.config.temperature,
        }

        try:
            t0 = time.time()
            resp = requests.post(url, headers=self._get_headers(), json=payload, timeout=self.config.request_timeout)
            latency = round(time.time() - t0, 3)
            if resp.status_code == 200:
                raw_text = resp.json()["choices"][0]["message"]["content"].strip()
                result = self._clean_and_parse_json(raw_text)
                result["_latency_seconds"] = latency
                result["_backend"] = f"Unsloth-API ({self.server_endpoint})"
                return result
            return {"error": f"http_{resp.status_code}", "_backend": "server_error"}
        except Exception as e:
            return {"error": str(e), "_backend": "request_exception"}

    def _call_unsloth_direct(self, pil_img: Image.Image, prompt: str, max_tokens: int) -> Dict[str, Any]:
        try:
            if self.unsloth_model is None:
                self.unsloth_model, self.unsloth_tokenizer = FastVisionModel.from_pretrained(
                    self.model_name,
                    load_in_4bit=True,
                    use_gradient_checkpointing="unsloth",
                )
                FastVisionModel.for_inference(self.unsloth_model)

            t0 = time.time()
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": pil_img},
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
            input_text = self.unsloth_tokenizer.apply_chat_template(messages, add_generation_prompt=True)
            inputs = self.unsloth_tokenizer(pil_img, input_text, add_special_tokens=False, return_tensors="pt").to("cuda")

            with torch.inference_mode():
                outputs = self.unsloth_model.generate(
                    **inputs,
                    max_new_tokens=max_tokens,
                    use_cache=True,
                    temperature=self.config.temperature,
                )

            gen_tokens = outputs[0][inputs.input_ids.shape[1]:]
            raw_text = self.unsloth_tokenizer.decode(gen_tokens, skip_special_tokens=True).strip()
            latency = round(time.time() - t0, 3)
            result = self._clean_and_parse_json(raw_text)
            result["_latency_seconds"] = latency
            result["_backend"] = "Unsloth-Direct"
            return result
        except Exception as e:
            return {"error": str(e), "_backend": "direct_exception"}

    def _fallback_rule_analysis(self, image_input: Any) -> Dict[str, Any]:
        return {
            "state": "in_field",
            "monster_density": "medium",
            "player_hp_status": "healthy",
            "minimap_target_xy": None,
            "recommended_action": "farm_here",
            "reasoning": "VLM server offline. Fast loop heuristic active.",
            "_backend": "Rule-Fallback",
        }

    # Pre-built Strategic Visual Classifications
    def query_initial_strategic_guidance(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        Initial AI Brain Query:
        1. Where is the player located?
        2. Should we fight or warp?
        3. If in town, where is the healer NPC and where is the teleport crystal?
        """
        prompt = (
            "You are an expert MMORPG AI strategic brain.\n"
            "Analyze this game screenshot and answer:\n"
            "1. Where is the player currently located? (Town, Field, Combat, WorldMap, Dead)\n"
            "2. Should the player fight monsters or warp/travel?\n"
            "3. If in Town: locate the Healer NPC (Heart icon on left) and Teleport Crystal (Blue pillar on right).\n"
            "Reply strictly with valid JSON without markdown:\n"
            "{\n"
            '  "location": "<Town|Field|Combat|WorldMap|Dead>",\n'
            '  "recommended_action": "<fight|warp|heal_in_town|open_map|respawn>",\n'
            '  "healer_npc_x": <int or null>,\n'
            '  "healer_npc_y": <int or null>,\n'
            '  "warp_crystal_x": <int or null>,\n'
            '  "warp_crystal_y": <int or null>,\n'
            '  "reasoning": "<brief explanation>"\n'
            "}"
        )
        return self.query_vlm(frame, prompt)

    def query_town_healer_and_crystal(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        Queries LLM/VLM for exact pixel coordinates of Healer (Heart NPC) and Teleport Crystal in Town.
        """
        prompt = (
            "Analyze this MMORPG town screenshot.\n"
            "1. Find the Healer / Heart NPC (left side of fountain with heart icon).\n"
            "2. Find the Teleport Crystal (glowing blue pillar monument on right side of fountain).\n"
            "Reply strictly with valid JSON without markdown:\n"
            "{\n"
            '  "healer_visible": <true/false>,\n'
            '  "healer_x": <int pixel x or null>,\n'
            '  "healer_y": <int pixel y or null>,\n'
            '  "crystal_visible": <true/false>,\n'
            '  "crystal_x": <int pixel x or null>,\n'
            '  "crystal_y": <int pixel y or null>,\n'
            '  "description": "<brief location description>"\n'
            "}"
        )
        return self.query_vlm(frame, prompt)

    def classify_game_state(self, frame: np.ndarray) -> Dict[str, Any]:
        prompt = (
            "You are an AI agent playing an MMORPG.\n"
            "Analyze this screenshot. Reply ONLY with valid JSON, no markdown:\n"
            "{\n"
            '  "state": "<dead|in_town|world_map_open|in_field|in_combat>",\n'
            '  "hp_ratio": <float 0.0-1.0>,\n'
            '  "monsters_visible": <true/false>,\n'
            '  "minimap_has_red_dots": <true/false>,\n'
            '  "teleport_crystal_visible": <true/false>,\n'
            '  "world_map_open": <true/false>,\n'
            '  "reasoning": "<one sentence>"\n'
            "}"
        )
        return self.query_vlm(frame, prompt)

    def find_town_teleport_crystal(self, frame: np.ndarray) -> Dict[str, Any]:
        prompt = (
            "Analyze this MMORPG game screenshot. "
            "Find the glowing BLUE Teleport Crystal - a tall blue glowing pillar in the town center near the fountain. "
            "Reply ONLY with valid JSON: "
            '{"crystal_visible": true/false, '
            '"crystal_x": <int CSS-pixel x center in this image or null>, '
            '"crystal_y": <int CSS-pixel y center or null>, '
            '"crystal_description": "<brief where>"}'
        )
        return self.query_vlm(frame, prompt)

    def analyze_field_targets(self, frame: np.ndarray) -> Dict[str, Any]:
        prompt = (
            "You are an AI agent controlling an MMORPG character.\n"
            "Minimap is TOP-RIGHT corner. Red dots = monsters.\n"
            "Reply ONLY valid JSON:\n"
            "{\n"
            '  "nearest_monster_x": <int or null>,\n'
            '  "nearest_monster_y": <int or null>,\n'
            '  "nearest_dot_x": <int or null in screenshot coords>,\n'
            '  "nearest_dot_y": <int or null>,\n'
            '  "hp_critical": <true/false>,\n'
            '  "action": "<click_minimap_dot|attack_monster|use_potion|rotate_camera>",\n'
            '  "reasoning": "<brief>"\n'
            "}"
        )
        return self.query_vlm(frame, prompt)
