import os
import sys
import json
import base64
import time
import cv2
import numpy as np
from PIL import Image
import io

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

def _load_dotenv(dotenv_path=None):
    """Loads environment variables from .env file into os.environ."""
    if dotenv_path is None:
        dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(dotenv_path):
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'").strip('"')
                    if key and key not in os.environ:
                        os.environ[key] = val

_load_dotenv()

DEFAULT_UNSLOTH_ENDPOINT = os.getenv("UNSLOTH_ENDPOINT", "http://127.0.0.1:8888/v1")
DEFAULT_UNSLOTH_MODEL = os.getenv("UNSLOTH_MODEL", "unsloth/Qwen2.5-VL-7B-Instruct-bnb-4bit")
DEFAULT_API_KEY = os.getenv("UNSLOTH_API_KEY", os.getenv("OPENAI_API_KEY", ""))


class QwenVLStrategicBrain:
    """
    Strategic AI Brain supporting:
    1. Unsloth Studio / Local API Server (http://127.0.0.1:8888/v1)
    2. Direct Unsloth FastVisionModel (Native 4-bit local GPU inference)
    3. Standby Rule-based Fallback
    """
    def __init__(
        self,
        backend="auto",
        server_endpoint=DEFAULT_UNSLOTH_ENDPOINT,
        model_name=DEFAULT_UNSLOTH_MODEL,
        api_key=DEFAULT_API_KEY,
        load_unsloth_immediately=False
    ):
        self.backend = backend.lower()
        self.server_endpoint = server_endpoint.rstrip('/')
        self.model_name = model_name
        self.api_key = api_key

        self.unsloth_model = None
        self.unsloth_tokenizer = None
        self.active_backend = "none"

        self._initialize_backend(load_unsloth_immediately)

    def _get_headers(self):
        """Builds HTTP request headers including authorization if present."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _initialize_backend(self, load_unsloth_immediately):
        """Selects and initializes the appropriate backend."""
        # 1. Check Unsloth API server (e.g. http://127.0.0.1:8888/v1)
        if self.backend in ["auto", "api", "server", "unsloth_api"]:
            if self._check_server_connection():
                self.active_backend = "server"
                return

        # 2. Check direct Unsloth FastVisionModel on GPU
        if self.backend in ["auto", "unsloth", "local"]:
            if HAS_UNSLOTH:
                print(f"[Qwen2.5-VL] Using direct Unsloth engine with {self.model_name}")
                if load_unsloth_immediately:
                    self._load_unsloth_model()
                self.active_backend = "unsloth_local"
                return
            elif self.backend == "unsloth":
                print("[Qwen2.5-VL Warning] Direct Unsloth package not imported.")

        # 3. Fallback mode
        print("[Qwen2.5-VL] No active Unsloth server or local engine available. Operating in Standby/Fallback mode.")
        self.active_backend = "fallback"

    def _check_server_connection(self):
        """Checks if Unsloth API server (127.0.0.1:8888) or other local server is active."""
        if not HAS_REQUESTS:
            return False

        candidate_endpoints = [
            self.server_endpoint,
            "http://127.0.0.1:8888/v1",
            "http://localhost:8888/v1",
            "http://localhost:8000/v1",
            "http://localhost:11434/v1"
        ]
        seen = set()
        endpoints_to_try = [e for e in candidate_endpoints if not (e in seen or seen.add(e))]

        for ep in endpoints_to_try:
            try:
                url = f"{ep}/models"
                headers = self._get_headers()
                resp = requests.get(url, headers=headers, timeout=2)
                if resp.status_code in [200, 401]:
                    if resp.status_code == 200:
                        data = resp.json().get('data', [])
                        if data:
                            self.model_name = data[0].get('id', self.model_name)
                    self.server_endpoint = ep
                    print(f"[Qwen2.5-VL] Connected to Unsloth API Server at {self.server_endpoint} (Model: {self.model_name})")
                    return True
            except Exception:
                continue
        return False

    def _load_unsloth_model(self):
        """Loads Unsloth FastVisionModel with 4-bit quantization on GPU."""
        if self.unsloth_model is not None:
            return

        print(f"[Unsloth] Loading {self.model_name} in 4-bit mode on CUDA...")
        t0 = time.time()
        self.unsloth_model, self.unsloth_tokenizer = FastVisionModel.from_pretrained(
            self.model_name,
            load_in_4bit=True,
            use_gradient_checkpointing="unsloth"
        )
        FastVisionModel.for_inference(self.unsloth_model)
        load_time = round(time.time() - t0, 2)
        print(f"[Unsloth] Model loaded successfully in {load_time}s")

    def _to_pil_image(self, image_input):
        """Converts input image to PIL Image instance."""
        if isinstance(image_input, Image.Image):
            return image_input

        if isinstance(image_input, str):
            if os.path.exists(image_input):
                return Image.open(image_input).convert("RGB")
            raise FileNotFoundError(f"Image not found: {image_input}")

        if isinstance(image_input, bytes):
            return Image.open(io.BytesIO(image_input)).convert("RGB")

        if isinstance(image_input, np.ndarray):
            rgb_arr = cv2.cvtColor(image_input, cv2.COLOR_BGR2RGB)
            return Image.fromarray(rgb_arr)

        raise ValueError(f"Unsupported image format: {type(image_input)}")

    def _encode_image_base64(self, pil_image):
        """Encodes PIL Image to base64 JPEG."""
        buffered = io.BytesIO()
        pil_image.save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def analyze_game_state(self, image_input, custom_prompt=None):
        """
        Executes high-level visual analysis on game screenshot.
        Returns structured decision dictionary.
        """
        pil_img = self._to_pil_image(image_input)

        default_prompt = (
            "You are an AI strategic brain analyzing an MMORPG game screenshot.\n"
            "Analyze the image and respond with ONLY a valid JSON object containing the following keys:\n"
            "1. 'monster_density': string ('low', 'medium', 'high')\n"
            "2. 'player_hp_status': string ('healthy', 'warning', 'critical')\n"
            "3. 'minimap_target_xy': array [x, y] of recommended target coordinates on minimap/screen, or null\n"
            "4. 'recommended_action': string ('farm_here', 'move_to_denser_area', 'retreat_heal', 'use_buff')\n"
            "5. 'reasoning': short text summary\n"
            "Respond strictly in valid JSON format without markdown formatting."
        )
        prompt = custom_prompt if custom_prompt else default_prompt

        if self.active_backend == "server":
            return self._call_server_api(pil_img, prompt)
        elif self.active_backend == "unsloth_local":
            return self._call_unsloth_direct(pil_img, prompt)
        else:
            return self._fallback_rule_analysis(image_input)

    def _call_server_api(self, pil_img, prompt):
        """Inference using Unsloth API server (http://127.0.0.1:8888/v1)."""
        base64_img = self._encode_image_base64(pil_img)
        url = f"{self.server_endpoint}/chat/completions"
        headers = self._get_headers()

        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_img}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 500,
            "temperature": 0.2
        }

        try:
            t0 = time.time()
            response = requests.post(url, headers=headers, json=payload, timeout=1.5)
            latency = round(time.time() - t0, 3)

            if response.status_code == 200:
                result = response.json()
                raw_text = result['choices'][0]['message']['content'].strip()
                parsed_json = self._clean_and_parse_json(raw_text)
                parsed_json['_latency_seconds'] = latency
                parsed_json['_backend'] = f"Unsloth-API ({self.server_endpoint})"
                return parsed_json
            else:
                print(f"[Unsloth API Error] Status {response.status_code}: {response.text}")
                return self._fallback_rule_analysis(None)
        except Exception as e:
            print(f"[Unsloth API Error] Request failed: {e}")
            return self._fallback_rule_analysis(None)

    def _call_unsloth_direct(self, pil_img, prompt):
        """Inference using local Unsloth FastVisionModel on GPU."""
        try:
            self._load_unsloth_model()
            t0 = time.time()

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": pil_img},
                        {"type": "text", "text": prompt}
                    ]
                }
            ]

            input_text = self.unsloth_tokenizer.apply_chat_template(messages, add_generation_prompt=True)
            inputs = self.unsloth_tokenizer(
                pil_img,
                input_text,
                add_special_tokens=False,
                return_tensors="pt"
            ).to("cuda")

            with torch.inference_mode():
                outputs = self.unsloth_model.generate(
                    **inputs,
                    max_new_tokens=256,
                    use_cache=True,
                    temperature=0.2
                )

            gen_tokens = outputs[0][inputs.input_ids.shape[1]:]
            raw_text = self.unsloth_tokenizer.decode(gen_tokens, skip_special_tokens=True).strip()
            latency = round(time.time() - t0, 3)

            parsed_json = self._clean_and_parse_json(raw_text)
            parsed_json['_latency_seconds'] = latency
            parsed_json['_backend'] = f"Unsloth-Direct ({self.model_name})"
            return parsed_json

        except Exception as e:
            print(f"[Unsloth Direct Error] Inference failed: {e}")
            return self._fallback_rule_analysis(None)

    def _clean_and_parse_json(self, raw_text):
        """Cleans markdown JSON wrappers and parses dictionary."""
        cleaned = raw_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {
                "monster_density": "medium",
                "player_hp_status": "healthy",
                "minimap_target_xy": [960, 480],
                "recommended_action": "farm_here",
                "reasoning": f"Raw VLM text fallback: {raw_text[:100]}"
            }

    def _fallback_rule_analysis(self, image_input):
        """Fallback heuristics when models/servers are offline."""
        return {
            "monster_density": "unknown",
            "player_hp_status": "healthy",
            "minimap_target_xy": None,
            "recommended_action": "farm_here",
            "reasoning": "Local VLM offline. Fast loop heuristic active.",
            "_backend": "Rule-Fallback"
        }


if __name__ == "__main__":
    brain = QwenVLStrategicBrain(server_endpoint="http://127.0.0.1:8888/v1")
    dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)
    print("Testing QwenVLStrategicBrain initialization with Unsloth API (http://127.0.0.1:8888/v1)...")
    result = brain.analyze_game_state(dummy_img)
    print("Result:", json.dumps(result, indent=2))
