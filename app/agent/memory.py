import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from config.settings import get_default_config


class MemoryEngine:
    """
    Persistent Spatial & Semantic Memory System for AI MMORPG Agent.
    Manages:
    1. Spatial Memory: Farming Hotspots, monster types, EXP rates.
    2. Policy Memory: Class skill combinations (e.g. Gunslinger AoE).
    3. Temporal Memory: Level progression, EXP gain events, death counts.
    """
    def __init__(self, memory_file: Optional[str] = None):
        if memory_file is None:
            config = get_default_config()
            memory_file = os.path.join(config.data_dir, "game_memory.json")
        self.memory_file = memory_file
        self.memory_data = self._load_memory()

    def _load_memory(self) -> Dict[str, Any]:
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        # Check root game_memory.json for migration
        root_memory = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "game_memory.json")
        if os.path.exists(root_memory):
            try:
                with open(root_memory, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._save_data(data)
                    return data
            except Exception:
                pass

        # Default structure
        default_data = {
            "character_profile": {
                "name": "Player",
                "class": "Gunslinger",
                "base_level": 80,
                "job_level": 45,
            },
            "farming_hotspots": [
                {
                    "name": "Stormreef Isle Hotspot 1",
                    "x": 455,
                    "y": 430,
                    "zone": "Stormreef Isle",
                    "mob_type": "Stormreef Mobs",
                    "exp_rate_hr": 120000,
                    "visits": 1,
                },
                {
                    "name": "Central Safe Zone",
                    "x": 960,
                    "y": 480,
                    "zone": "Midgard Field",
                    "mob_type": "Viewport Mobs",
                    "exp_rate_hr": 60000,
                    "visits": 1,
                },
            ],
            "skill_policies": {
                "Gunslinger_AoE": {
                    "buff_skill": "6",
                    "pull_combo": ["3", "Y", "T"],
                    "aoe_at_mouse": ["1"],
                    "single_target_at_mouse": ["2", "Q"],
                    "dodge_skill": "4",
                    "heal_skill": "5",
                    "skill_descriptions": {
                        "1": "AoE at mouse position",
                        "2": "Single target at mouse position",
                        "Q": "Single target at mouse position",
                        "3": "Pull monsters inside circle at mouse position",
                        "4": "Dodge jump",
                        "5": "Healing potion / skill",
                        "6": "Buff activation",
                        "Y": "Prerequisite for T",
                        "T": "AoE around self (Requires 3 then Y before T)",
                    },
                }
            },
            "stats": {
                "total_kills": 0,
                "total_deaths": 0,
                "total_warps": 0,
                "total_potions_used": 0,
            },
            "exp_history": [],
        }
        self._save_data(default_data)
        return default_data

    def _save_data(self, data: Dict[str, Any]):
        os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
        with open(self.memory_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def save(self):
        self._save_data(self.memory_data)

    def record_kill(self, mob_name: str = "monster", exp_gain: int = 0, gold_gain: int = 0):
        stats = self.memory_data.setdefault("stats", {})
        stats["total_kills"] = stats.get("total_kills", 0) + 1
        if exp_gain > 0 or gold_gain > 0:
            self.log_exp_gain(exp_gain, gold_gain)
        else:
            self.save()

    def record_death(self, location: str = "Field"):
        stats = self.memory_data.setdefault("stats", {})
        stats["total_deaths"] = stats.get("total_deaths", 0) + 1
        self.save()

    def record_potion(self):
        stats = self.memory_data.setdefault("stats", {})
        stats["total_potions_used"] = stats.get("total_potions_used", 0) + 1

    def log_exp_gain(self, base_exp: int, job_exp: int = 0, gold: int = 0):
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "base_exp": base_exp,
            "job_exp": job_exp,
            "gold": gold,
        }
        self.memory_data.setdefault("exp_history", []).append(entry)
        self.save()

    def record_farming_spot(self, name: str, coords: Tuple[int, int], zone: str, mob_type: str, exp_rate: int):
        spot = {
            "name": name,
            "x": coords[0],
            "y": coords[1],
            "zone": zone,
            "mob_type": mob_type,
            "exp_rate_hr": exp_rate,
            "visits": 1,
        }
        self.memory_data.setdefault("farming_hotspots", []).append(spot)
        self.save()

    def get_optimal_farming_spot(self) -> Dict[str, Any]:
        spots = self.memory_data.get("farming_hotspots", [])
        if spots:
            return max(spots, key=lambda s: s.get("exp_rate_hr", 0))
        return {"name": "Default Spot", "x": 455, "y": 430, "zone": "Stormreef Isle"}

    def get_skill_policy(self, policy_name: str = "Gunslinger_AoE") -> Dict[str, Any]:
        return self.memory_data.get("skill_policies", {}).get(policy_name, {})
