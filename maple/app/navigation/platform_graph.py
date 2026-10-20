from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import yaml


@dataclass
class Platform:
    id: str
    y: int
    x_min: int
    x_max: int
    name: str = ""

    def contains_x(self, x: int) -> bool:
        return self.x_min <= x <= self.x_max

    def clamp_x(self, x: int) -> int:
        return max(self.x_min, min(self.x_max, x))


@dataclass
class PlatformEdge:
    source_id: str
    target_id: str
    action: str  # "WALK", "FLASH_JUMP", "DOWN_JUMP", "ROPE_LIFT", "LADDER", "PORTAL"
    cost: float = 1.0
    required_x_range: Optional[Tuple[int, int]] = None


class PlatformGraph:
    """
    2D Platform Graph for MapleStory map topology.
    Manages platforms, vertical drop zones (Down+Jump), and ascension points (Rope Lift / Ladders).
    """

    def __init__(self):
        self.platforms: Dict[str, Platform] = {}
        self.edges: Dict[str, List[PlatformEdge]] = {}

    def add_platform(self, plat: Platform):
        self.platforms[plat.id] = plat
        if plat.id not in self.edges:
            self.edges[plat.id] = []

    def add_edge(self, edge: PlatformEdge):
        if edge.source_id not in self.edges:
            self.edges[edge.source_id] = []
        self.edges[edge.source_id].append(edge)

    def find_platform(self, x: int, y: int, tolerance_y: int = 15) -> Optional[Platform]:
        """
        Finds the platform corresponding to minimap coordinate (x, y).
        Matches closest platform in Y where x falls within x_min and x_max.
        """
        best_plat = None
        min_dy = float("inf")

        for plat in self.platforms.values():
            if plat.contains_x(x):
                dy = abs(plat.y - y)
                if dy <= tolerance_y and dy < min_dy:
                    min_dy = dy
                    best_plat = plat

        # If x is slightly outside, find closest platform overall
        if best_plat is None:
            for plat in self.platforms.values():
                dy = abs(plat.y - y)
                if dy <= tolerance_y:
                    dist_x = min(abs(plat.x_min - x), abs(plat.x_max - x))
                    if dist_x < 20 and dy < min_dy:
                        min_dy = dy
                        best_plat = plat

        return best_plat

    @classmethod
    def from_dict(cls, data: Dict) -> "PlatformGraph":
        graph = cls()
        for p_data in data.get("platforms", []):
            plat = Platform(
                id=p_data["id"],
                y=p_data["y"],
                x_min=p_data["x_min"],
                x_max=p_data["x_max"],
                name=p_data.get("name", ""),
            )
            graph.add_platform(plat)

        for e_data in data.get("connections", []):
            req_x = None
            if "x_range" in e_data:
                req_x = tuple(e_data["x_range"])
            edge = PlatformEdge(
                source_id=e_data["from"],
                target_id=e_data["to"],
                action=e_data["action"],
                cost=e_data.get("cost", 1.0),
                required_x_range=req_x,
            )
            graph.add_edge(edge)

        return graph

    @classmethod
    def load_from_yaml(cls, yaml_path: str) -> "PlatformGraph":
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)
