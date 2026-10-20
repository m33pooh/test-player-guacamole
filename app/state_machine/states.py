from enum import Enum


class BotState(str, Enum):
    UNKNOWN = "UNKNOWN"
    DEAD = "DEAD"
    IN_TOWN = "IN_TOWN"
    OPEN_MAP = "OPEN_MAP"
    WARP = "WARP"
    IN_FIELD = "IN_FIELD"
    COMBAT = "COMBAT"
    LOOT = "LOOT"
    HEAL = "HEAL"
    RECOVER = "RECOVER"
