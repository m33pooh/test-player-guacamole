import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from app.vision.state import GameState
from config.settings import LLMConfig


@dataclass
class StrategicDecision:
    target_zone: str = "Stormreef Isle"
    action_priority: str = "farm"  # 'farm', 'retreat_town', 'heal_recover', 'explore'
    skill_strategy: str = "aoe_heavy"  # 'aoe_heavy', 'single_burst', 'defensive'
    retreat_hp_threshold: float = 0.30
    inventory_threshold: float = 0.90
    reasoning: str = "Standard farming routine"
    suggested_spot: Optional[Dict[str, Any]] = None
    extra: Dict[str, Any] = field(default_factory=dict)


class BaseLLMPlanner(ABC):
    """
    Abstract Base Class for LLM Strategic Planner.
    Enables plug-and-play LLM engines (OpenRouter, OpenAI, Gemini, Ollama, Custom API, or Stub).
    """
    @abstractmethod
    def plan(
        self,
        game_state: GameState,
        metrics_summary: Dict[str, Any],
        memory_data: Dict[str, Any],
    ) -> StrategicDecision:
        pass


class StubRuleBasedPlanner(BaseLLMPlanner):
    """
    Default High-Speed Rule-Based Planner.
    Executes strategic reasoning based on state heuristics without requiring external API keys.
    """
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()

    def plan(
        self,
        game_state: GameState,
        metrics_summary: Dict[str, Any],
        memory_data: Dict[str, Any],
    ) -> StrategicDecision:
        # Check Death
        if game_state.dead:
            return StrategicDecision(
                target_zone="Town",
                action_priority="heal_recover",
                skill_strategy="defensive",
                reasoning="Player dead. Initiating town respawn & recovery cycle.",
            )

        # Check Inventory Capacity
        if game_state.inventory >= 0.90:
            return StrategicDecision(
                target_zone="Town",
                action_priority="retreat_town",
                skill_strategy="defensive",
                reasoning="Inventory near capacity (>90%). Returning to town to sell/store loot.",
            )

        # Check Critical HP
        if game_state.character_hp < 0.25:
            return StrategicDecision(
                target_zone="Town" if game_state.in_town else "Field",
                action_priority="heal_recover",
                skill_strategy="defensive",
                reasoning="Character HP critical (<25%). Activating defensive heal policy.",
            )

        # High Monster Density AoE Farming
        if game_state.enemy_count >= 2:
            return StrategicDecision(
                target_zone="Stormreef Isle",
                action_priority="farm",
                skill_strategy="aoe_heavy",
                reasoning=f"High enemy density detected ({game_state.enemy_count} mobs). Using Pull + AoE rotation.",
            )

        # Default Spot Farming
        return StrategicDecision(
            target_zone="Stormreef Isle",
            action_priority="farm",
            skill_strategy="aoe_heavy",
            reasoning="Normal field state. Proceeding with active grinding.",
        )


class OpenRouterLLMPlanner(BaseLLMPlanner):
    """
    Strategic LLM Planner connecting to OpenRouter API (https://openrouter.ai/docs/api_reference/overview).
    Supports models like Qwen 2.5 72B, Llama 3.3 70B, Gemini 2.0 Flash, Claude 3.5 Sonnet, GPT-4o, etc.
    """
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self.fallback_planner = StubRuleBasedPlanner(self.config)

    def _build_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
        }
        if self.config.site_url:
            headers["HTTP-Referer"] = self.config.site_url
        if self.config.site_name:
            headers["X-Title"] = self.config.site_name
        return headers

    def plan(
        self,
        game_state: GameState,
        metrics_summary: Dict[str, Any],
        memory_data: Dict[str, Any],
    ) -> StrategicDecision:
        if game_state.dead or not self.config.api_key or not HAS_REQUESTS:
            return self.fallback_planner.plan(game_state, metrics_summary, memory_data)

        prompt = (
            "You are an AI strategic decision planner for an MMORPG automation agent.\n"
            "Analyze the current game state, historical performance metrics, and memory to decide the optimal high-level strategy.\n\n"
            "Respond ONLY with a valid JSON object matching this schema:\n"
            "{\n"
            '  "target_zone": "<Stormreef Isle|Midgard Field|Town>",\n'
            '  "action_priority": "<farm|retreat_town|heal_recover|explore>",\n'
            '  "skill_strategy": "<aoe_heavy|single_burst|defensive>",\n'
            '  "retreat_hp_threshold": <float between 0.1 and 0.5>,\n'
            '  "reasoning": "<one concise sentence explaining your strategic rationale>"\n'
            "}\n\n"
            f"Current GameState: {json.dumps(game_state.to_dict(), default=lambda o: int(o) if hasattr(o, 'item') and isinstance(o.item(), int) else (float(o) if hasattr(o, 'item') and isinstance(o.item(), float) else str(o)))}\n"
            f"Metrics Summary: {json.dumps(metrics_summary, default=lambda o: int(o) if hasattr(o, 'item') and isinstance(o.item(), int) else (float(o) if hasattr(o, 'item') and isinstance(o.item(), float) else str(o)))}\n"
            f"Memory Hotspots: {json.dumps(memory_data.get('farming_hotspots', []), default=lambda o: int(o) if hasattr(o, 'item') and isinstance(o.item(), int) else (float(o) if hasattr(o, 'item') and isinstance(o.item(), float) else str(o)))}\n"
        )

        headers = self._build_headers()
        payload = {
            "model": self.config.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an expert MMORPG AI strategic planner. "
                        "Respond strictly with valid JSON without markdown tags."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "response_format": {"type": "json_object"},
        }

        try:
            url = f"{self.config.api_base.rstrip('/')}/chat/completions"
            t0 = time.time()
            resp = requests.post(url, headers=headers, json=payload, timeout=10.0)
            latency = round(time.time() - t0, 3)

            if resp.status_code == 200:
                result_json = resp.json()
                choices = result_json.get("choices", [])
                if choices and "message" in choices[0]:
                    raw = choices[0]["message"].get("content", "").strip()
                    data = self._parse_json_safely(raw)
                    if data and isinstance(data, dict):
                        return StrategicDecision(
                            target_zone=data.get("target_zone", "Stormreef Isle"),
                            action_priority=data.get("action_priority", "farm"),
                            skill_strategy=data.get("skill_strategy", "aoe_heavy"),
                            retreat_hp_threshold=float(data.get("retreat_hp_threshold", 0.30)),
                            reasoning=f"[OpenRouter ({self.config.model_name}) {latency}s] {data.get('reasoning', '')}",
                            extra={"latency": latency, "model": self.config.model_name},
                        )
            else:
                print(f"[OpenRouter Notice] Status {resp.status_code}: {resp.text[:120]} (Using rule heuristic)", flush=True)
        except Exception as e:
            print(f"[OpenRouter Notice] Request error: {e} (Using rule heuristic)", flush=True)

        return self.fallback_planner.plan(game_state, metrics_summary, memory_data)

    def _parse_json_safely(self, raw: str) -> Optional[Dict[str, Any]]:
        import re
        if not raw:
            return None
        cleaned = raw.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()

        try:
            return json.loads(cleaned)
        except Exception:
            pass

        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
        return None


# Alias for backwards compatibility
ExternalAPILLMPlanner = OpenRouterLLMPlanner


def create_planner(config: Optional[LLMConfig] = None) -> BaseLLMPlanner:
    """Factory function for LLM Strategic Planner."""
    cfg = config or LLMConfig()
    if cfg.api_key and cfg.provider not in ["stub", "none"]:
        return OpenRouterLLMPlanner(cfg)
    return StubRuleBasedPlanner(cfg)
