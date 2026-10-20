import time
from typing import Any, Dict, List, Optional

from app.agent.memory import MemoryEngine
from app.agent.planner import BaseLLMPlanner, StrategicDecision
from app.vision.state import GameState


# Gunslinger Fine-Tuned Skill Timing Rules
SKILL_3_VORTEX_DURATION = 4.5   # Sucks monsters into vortex; lasts 4.5s; recast every 4.5s to continuously lock mobs
SKILL_1_AOE_COOLDOWN = 1.8      # Primary spam AoE blast; 1.8s cooldown (cast 4-5x more often than 3)
SKILL_Y_SNIPER_COOLDOWN = 6.0   # Gunshot sniper skill; 6.0s cooldown; requires mouse hovered on target
SKILL_T_NOVA_COOLDOWN = 6.0     # Explosion around character; MUST BE USED ONLY IMMEDIATELY AFTER SKILL Y
SKILL_E_MARK_COOLDOWN = 8.0     # Hunter's Mark debuff; used ONLY on Big/Elite monsters; requires mouse hovered on target
SKILL_Q_RAPID_COOLDOWN = 0.35   # Gunshot rapid spammable attack; requires mouse hovered on target
SKILL_4_DODGE_COOLDOWN = 5.0    # Jump dodge away if overwhelmed
SKILL_5_POTION = "5"            # Emergency HP recovery potion
SKILL_6_BUFF = "6"              # Gunslinger combat buff (20s maintenance)


class AgentPolicyEngine:
    """
    Translates high-level strategic planner decisions, memory, and tactical combat rules
    into fine-grained skill rotations for the Gunslinger class.
    """
    def __init__(self, memory: MemoryEngine, planner: BaseLLMPlanner):
        self.memory = memory
        self.planner = planner
        self.current_decision: StrategicDecision = StrategicDecision()

    def update_strategic_plan(self, game_state: GameState, metrics_summary: Dict[str, Any]) -> StrategicDecision:
        decision = self.planner.plan(game_state, metrics_summary, self.memory.memory_data)
        self.current_decision = decision
        return decision

    def get_combat_combo(self, target_type: str = "cluster", is_big_monster: bool = False) -> List[str]:
        """
        Retrieves baseline skill sequence based on target classification.
        """
        if is_big_monster:
            # Big monster priority: Mark E -> Q rapid burst -> Y -> T combo + 1 & 3 maintenance
            return ["E", "Q", "Y", "T", "1", "3"]
        elif target_type == "cluster":
            # AoE heavy pull & blast
            return ["3", "1", "Y", "T", "Q"]
        else:
            # Standard single target
            return ["1", "Y", "T", "Q"]

    def get_potion_key(self) -> str:
        return SKILL_5_POTION

    def get_buff_key(self) -> str:
        return SKILL_6_BUFF

    def get_dodge_key(self) -> str:
        return "4"
