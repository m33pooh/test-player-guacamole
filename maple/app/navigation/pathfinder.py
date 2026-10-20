import heapq
from typing import Dict, List, Optional, Tuple, Any
from maple.app.navigation.platform_graph import Platform, PlatformEdge, PlatformGraph


class Pathfinder:
    """
    A* Pathfinder on 2D MapleStory Platform Graphs.
    Computes optimal sequence of movements (Flash Jump, Walk, Down+Jump, Rope Lift)
    to navigate between arbitrary minimap coordinates.
    """

    def __init__(self, graph: PlatformGraph):
        self.graph = graph

    def plan_path(
        self,
        start_x: int,
        start_y: int,
        target_x: int,
        target_y: int,
    ) -> List[Dict[str, Any]]:
        """
        Calculates execution steps from (start_x, start_y) to (target_x, target_y).
        Returns a list of action dictionaries.
        """
        start_plat = self.graph.find_platform(start_x, start_y)
        target_plat = self.graph.find_platform(target_x, target_y)

        # Direct horizontal navigation if on same platform or graph missing
        if start_plat is None or target_plat is None or start_plat.id == target_plat.id:
            return self._build_horizontal_steps(start_x, target_x, target_y)

        # A* Search across platforms
        # Priority queue stores: (f_score, current_platform_id, path_edges)
        open_set = [(0.0, start_plat.id, [])]
        g_scores: Dict[str, float] = {start_plat.id: 0.0}
        visited = set()

        final_edges = None

        while open_set:
            f, curr_id, edge_path = heapq.heappop(open_set)

            if curr_id == target_plat.id:
                final_edges = edge_path
                break

            if curr_id in visited:
                continue
            visited.add(curr_id)

            curr_plat = self.graph.platforms[curr_id]
            curr_g = g_scores[curr_id]

            for edge in self.graph.edges.get(curr_id, []):
                next_id = edge.target_id
                next_plat = self.graph.platforms.get(next_id)
                if not next_plat:
                    continue

                tentative_g = curr_g + edge.cost
                if next_id not in g_scores or tentative_g < g_scores[next_id]:
                    g_scores[next_id] = tentative_g
                    # Heuristic: vertical distance + horizontal distance to target
                    h = abs(next_plat.y - target_plat.y) * 1.5 + abs(
                        ((next_plat.x_min + next_plat.x_max) / 2) - target_x
                    ) * 0.5
                    heapq.heappush(open_set, (tentative_g + h, next_id, edge_path + [edge]))

        if not final_edges:
            # Fallback direct approach
            return self._build_horizontal_steps(start_x, target_x, target_y)

        # Convert platform edges into concrete movement instructions
        steps: List[Dict[str, Any]] = []
        curr_x = start_x

        for edge in final_edges:
            src_plat = self.graph.platforms[edge.source_id]
            tgt_plat = self.graph.platforms[edge.target_id]

            # 1. Walk to transition point if required
            transition_x = curr_x
            if edge.required_x_range:
                min_rx, max_rx = edge.required_x_range
                if not (min_rx <= curr_x <= max_rx):
                    transition_x = (min_rx + max_rx) // 2
                    steps.extend(self._build_horizontal_steps(curr_x, transition_x, src_plat.y))
                    curr_x = transition_x

            # 2. Add transition action
            steps.append({
                "action": edge.action,
                "direction": "up" if edge.action == "ROPE_LIFT" else ("down" if edge.action == "DOWN_JUMP" else None),
                "target_y": tgt_plat.y,
                "target_plat": tgt_plat.id,
            })
            curr_x = tgt_plat.clamp_x(curr_x)

        # Final horizontal alignment on target platform
        steps.extend(self._build_horizontal_steps(curr_x, target_x, target_plat.y))
        return steps

    def _build_horizontal_steps(self, from_x: int, to_x: int, y: int) -> List[Dict[str, Any]]:
        dx = to_x - from_x
        if abs(dx) < 4:
            return []

        direction = "right" if dx > 0 else "left"
        dist = abs(dx)

        if dist > 30:
            # High speed Flash Jump
            return [
                {
                    "action": "FLASH_JUMP",
                    "direction": direction,
                    "target_x": to_x,
                    "target_y": y,
                    "distance": dist,
                }
            ]
        else:
            # Precise Walk
            return [
                {
                    "action": "WALK",
                    "direction": direction,
                    "target_x": to_x,
                    "target_y": y,
                    "distance": dist,
                }
            ]
