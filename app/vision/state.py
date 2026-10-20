import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any


@dataclass
class TargetInfo:
    x: int
    y: int
    target_type: str = "single"  # 'single', 'cluster', 'radar_dot'
    mob_count: int = 1
    is_big: bool = False
    distance_to_player: float = 0.0
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)


@dataclass
class MinimapNavigationVector:
    norm_dx: float
    norm_dy: float
    distance: float
    player_pos: Tuple[int, int]
    target_dot: Tuple[int, int]
    total_mobs: int
    screen_dx: float = 0.0
    screen_dy: float = 0.0


@dataclass
class GameState:
    """
    Structured Game State representation matching Section 4 of AI_MORPG_Farming_Agent.md
    """
    location: str = "Unknown"
    character_hp: float = 1.0  # 0.0 - 1.0
    character_mp: float = 1.0  # 0.0 - 1.0
    target: Optional[str] = None
    target_pos: Optional[Tuple[int, int]] = None
    target_distance: float = 0.0
    target_is_big: bool = False
    inventory: float = 0.0  # 0.0 - 1.0 capacity ratio
    enemy_count: int = 0
    dead: bool = False
    stuck: bool = False
    in_town: bool = False
    world_map_open: bool = False
    character_select: bool = False
    disconnection_modal: bool = False
    
    # Navigation and Vision telemetry
    minimap_vector: Optional[MinimapNavigationVector] = None
    active_target: Optional[TargetInfo] = None
    detected_enemies: List[Tuple[int, int]] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "location": str(self.location),
            "character_hp": float(round(self.character_hp, 3)),
            "character_mp": float(round(self.character_mp, 3)),
            "target": str(self.target) if self.target else None,
            "target_pos": [int(p) for p in self.target_pos] if self.target_pos else None,
            "target_distance": float(round(self.target_distance, 1)),
            "target_is_big": bool(self.target_is_big),
            "inventory": float(round(self.inventory, 3)),
            "enemy_count": int(self.enemy_count),
            "dead": bool(self.dead),
            "stuck": bool(self.stuck),
            "in_town": bool(self.in_town),
            "world_map_open": bool(self.world_map_open),
            "timestamp": float(round(self.timestamp, 2)),
        }
