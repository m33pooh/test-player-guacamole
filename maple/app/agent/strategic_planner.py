import json
import os
from typing import Dict, Any, Optional, List
import requests


class StrategicPlanner:
    """
    Strategic LLM Planner (Slow Loop, every 5-15 mins).
    Implements Section 5 of maplev2.md:
    - 5.1 One-Shot Check: compares kills/min against max map spawn cap to recommend damage buffs or map adjustments.
    - 5.2 Dynamic Summon Optimization: analyzes unkilled mob heatmap to recommend optimal [x, y] placement for Sol Janus / Erda Fountain.
    - 5.3 Loot Cycle & Multiplier advisory.
    """

    def __init__(
        self,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_base = api_base or os.getenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.model = model or os.getenv("LLM_MODEL", "nvidia/nemotron-3.5-lightning:free")

    def evaluate_one_shot_efficiency(
        self,
        current_kpm: float,
        max_spawn_cap: float = 290.0,
    ) -> Dict[str, Any]:
        """
        One-Shot Check (Section 5.1):
        Assesses if skills are one-shotting mobs based on theoretical spawn cap.
        """
        ratio = current_kpm / max(1.0, max_spawn_cap)
        if ratio >= 0.90:
            status = "OPTIMAL_ONE_SHOT"
            action = "Maintain current map and skill tier."
        elif ratio >= 0.70:
            status = "SUBOPTIMAL_BURST_NEEDED"
            action = "Activate attack potion or guild buff to secure one-shot."
        else:
            status = "DAMAGE_DEFICIT"
            action = "Recommend downgrading to lower level map for higher net EXP/hr."

        return {
            "efficiency_ratio": round(ratio, 3),
            "status": status,
            "recommendation": action,
        }

    def optimize_summon_placement(
        self,
        residual_mob_positions: List[List[int]],
        current_summon_pos: List[int],
    ) -> List[int]:
        """
        Dynamic Summon Optimization (Section 5.2):
        Calculates centroid of residual (unkilled) mobs to shift summon location.
        """
        if not residual_mob_positions:
            return current_summon_pos

        avg_x = int(sum(p[0] for p in residual_mob_positions) / len(residual_mob_positions))
        avg_y = int(sum(p[1] for p in residual_mob_positions) / len(residual_mob_positions))
        print(f"[StrategicPlanner] Summon Heatmap Shift: Repositioning summon towards ({avg_x}, {avg_y})", flush=True)
        return [avg_x, avg_y]

    def evaluate_rotation_efficiency(
        self,
        metrics: Dict[str, Any],
        map_name: str,
        current_rotation: str,
    ) -> Dict[str, Any]:
        """
        Comprehensive LLM review of rotation and telemetry.
        """
        if not self.api_key:
            return {
                "recommendation": "Maintain current rotation profile.",
                "status": "api_key_missing",
            }

        prompt = (
            f"You are an AI optimization strategist for MapleStory farming.\n"
            f"Map: {map_name}\n"
            f"Current Rotation: {current_rotation}\n"
            f"Metrics: Kills/min={metrics.get('kills_per_minute', 0)}, "
            f"Rune Success Rate={metrics.get('rune_success_rate', 100)}%, "
            f"Channel Swaps={metrics.get('channel_swaps', 0)}\n\n"
            f"Provide a brief evaluation: Is the current route optimal, or should summon placement / waypoint timing be shifted? "
            f"Reply with JSON: {{\"status\": \"optimal\"|\"adjust\", \"recommendation\": \"...\", \"summon_shift\": \"left\"|\"right\"|\"keep\"}}"
        )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 150,
            "temperature": 0.2,
        }

        try:
            url = f"{self.api_base.rstrip('/')}/chat/completions"
            resp = requests.post(url, headers=headers, json=payload, timeout=8.0)
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                clean = content.strip()
                if clean.startswith("```json"):
                    clean = clean[7:]
                if clean.endswith("```"):
                    clean = clean[:-3]
                return json.loads(clean.strip())
            else:
                return {"recommendation": "Maintain current route (HTTP error)", "status": "error"}
        except Exception as e:
            return {"recommendation": f"Maintain current route ({e})", "status": "exception"}
