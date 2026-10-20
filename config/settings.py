import os
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


def _load_env_file(dotenv_path=None):
    """Loads environment variables from .env file."""
    if dotenv_path is None:
        dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(dotenv_path):
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v


_load_env_file()


@dataclass
class VisionConfig:
    screen_width: int = 1920
    screen_height: int = 1080
    use_yolo: bool = True
    yolo_model_path: str = os.getenv("YOLO_MODEL_PATH", "yolo11n.pt")
    confidence_threshold: float = 0.35
    hp_heal_threshold: float = 0.40
    hp_critical_threshold: float = 0.20
    # Minimap bounds (calibrated for 1920x1080 viewport)
    minimap_crop: Tuple[int, int, int, int] = (1450, 10, 1910, 255)


@dataclass
class VLMConfig:
    server_endpoint: str = os.getenv("UNSLOTH_ENDPOINT", "http://127.0.0.1:8888/v1")
    model_name: str = os.getenv("UNSLOTH_MODEL", "unsloth/Qwen3-VL-4B-Instruct-GGUF")
    api_key: str = os.getenv("UNSLOTH_API_KEY", "")
    request_timeout: float = 20.0
    temperature: float = 0.1
    max_tokens: int = 300


@dataclass
class LLMConfig:
    """
    Pluggable LLM configuration supporting OpenRouter, OpenAI, Gemini, Ollama, and Custom APIs.
    """
    provider: str = os.getenv("LLM_PROVIDER", "openrouter")  # 'openrouter', 'openai', 'gemini', 'custom', 'stub'
    api_base: str = os.getenv(
        "LLM_API_BASE",
        os.getenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")
    )
    api_key: str = os.getenv(
        "OPENROUTER_API_KEY",
        os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", ""))
    )
    model_name: str = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")
    site_url: str = os.getenv("OPENROUTER_SITE_URL", "https://github.com/mmorpg-ai-agent")
    site_name: str = os.getenv("OPENROUTER_SITE_NAME", "MMORPG-AI-Farming-Agent")
    temperature: float = 0.2
    max_tokens: int = 500
    planning_interval_seconds: float = 15.0


@dataclass
class ControllerConfig:
    backend: str = os.getenv("CONTROLLER_BACKEND", "auto")  # 'playwright', 'os', 'auto'
    cdp_url: str = os.getenv("CDP_URL", "http://127.0.0.1:9222")
    guacamole_url: str = os.getenv(
        "GUACAMOLE_URL",
        "http://localhost:60289/guacamole/#/client/UkRQIENvbm5lY3Rpb24AYwBkZWZhdWx0",
    )
    viewport_width: int = 1920
    viewport_height: int = 1080
    failsafe_enabled: bool = True
    key_delay: float = 0.03


@dataclass
class GameCoordsConfig:
    # 1920x1080 calibrated coordinates
    center_viewport: Tuple[int, int] = (960, 540)
    stormreef_isle: Tuple[int, int] = (512, 497)
    warp_btn: Tuple[int, int] = (1820, 1030)
    respawn_modal_buttons: List[Tuple[int, int]] = field(
        default_factory=lambda: [(960, 815), (960, 820), (960, 830), (837, 665), (960, 665)]
    )
    town_crystal_approx: Tuple[int, int] = (1240, 460)


@dataclass
class AgentConfig:
    vision: VisionConfig = field(default_factory=VisionConfig)
    vlm: VLMConfig = field(default_factory=VLMConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    controller: ControllerConfig = field(default_factory=ControllerConfig)
    coords: GameCoordsConfig = field(default_factory=GameCoordsConfig)
    data_dir: str = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    logs_dir: str = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")


def get_default_config() -> AgentConfig:
    config = AgentConfig()
    os.makedirs(config.data_dir, exist_ok=True)
    os.makedirs(config.logs_dir, exist_ok=True)
    return config
