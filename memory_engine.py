import os
import json
import time

MEMORY_FILE_PATH = os.path.join(os.path.dirname(__file__), "game_memory.json")

class MemoryEngine:
    """
    Mnemosyne-inspired Memory System for AI MMORPG Agent (AI_MMORPG_Strategies.md)
    Persists and manages:
    1. World Map & Monster Spawn Hotspots (Spatial Memory)
    2. Combat Skill Policies (Voyager Code-as-Policies Memory)
    3. Level Progression & EXP Efficiency History
    4. NPC & Quest Location Database
    """
    def __init__(self, memory_file=MEMORY_FILE_PATH):
        self.memory_file = memory_file
        self.memory_data = self._load_memory()

    def _load_memory(self):
        """Loads memory data from JSON database file"""
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[Memory Warning] Failed to read memory file: {e}. Initializing fresh memory.")
        
        # Default Memory Structure
        return {
            "character_profile": {
                "name": "M33POOH",
                "class": "Gunslinger",
                "base_level": 80,
                "job_level": 45,
            },
            "farming_hotspots": [
                {"name": "Central Safe Zone Spot 1", "x": 960, "y": 480, "mob_type": "Viewport Mobs", "exp_rate_hr": 55000},
                {"name": "Central Safe Zone Spot 2", "x": 920, "y": 450, "mob_type": "Viewport Mobs", "exp_rate_hr": 58000}
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
                        "Y": "Prerequisite for T",
                        "T": "AoE around self (Requires 3 then Y before T)"
                    }
                }
            },
            "exp_history": []
        }

    def save_memory(self):
        """Persists memory data to disk"""
        try:
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(self.memory_data, f, indent=2, ensure_ascii=False)
            print("[Memory Engine] Persistent state saved to game_memory.json")
        except Exception as e:
            print(f"[Memory Error] Failed to save memory: {e}")

    def log_exp_gain(self, base_exp, job_exp):
        """Logs EXP progress entry into temporal memory"""
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "base_exp": base_exp,
            "job_exp": job_exp
        }
        self.memory_data["exp_history"].append(entry)
        self.save_memory()

    def record_farming_spot(self, location_name, coords, mob_type, exp_rate):
        """Saves a high-density monster spawn location to spatial memory"""
        spot = {
            "name": location_name,
            "x": coords[0],
            "y": coords[1],
            "mob_type": mob_type,
            "exp_rate_hr": exp_rate
        }
        self.memory_data["farming_hotspots"].append(spot)
        self.save_memory()
        print(f"[Memory Engine] Learned new farming spot: {location_name} at {coords}")

    def get_optimal_farming_spot(self):
        """Retrieves highest EXP/hr farming spot from memory"""
        spots = self.memory_data.get("farming_hotspots", [])
        if spots:
            best = max(spots, key=lambda s: s.get("exp_rate_hr", 0))
            return best
        return {"name": "Default Spot", "x": 1820, "y": 80}

    def get_skill_policy(self, policy_name="Gunslinger_AoE"):
        """Retrieves stored combat skill policy"""
        return self.memory_data.get("skill_policies", {}).get(policy_name)

if __name__ == "__main__":
    memory = MemoryEngine()
    print("=== Testing Memory Engine (Mnemosyne System) ===")
    best_spot = memory.get_optimal_farming_spot()
    print(f"Optimal Farming Spot in Memory: {best_spot['name']} at ({best_spot['x']}, {best_spot['y']})")
    policy = memory.get_skill_policy()
    print(f"Loaded Skill Policy: {policy['aoe_combo']}")
