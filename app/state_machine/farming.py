import time
from typing import List, Optional, Tuple

from app.controller.controller import ActionController
from app.state_machine.combat import sanitize_combat_coordinates
from app.vision.state import GameState


class FarmingStateHandler:
    """
    Farming and Field Navigation Handler.
    Rules:
    1. NEVER click inside the Minimap HUD UI (x > 75% or y < 28%) to prevent opening World Map.
    2. Translates 2D Minimap vectors into 3D Isometric Screen ground space.
    3. Double-clicks on ground in monster direction and pulses directional keys.
    4. Closed-loop stuck prevention: If minimap position doesn't change, jumps/slides into open space.
    """
    def __init__(self, controller: ActionController):
        self.controller = controller
        self.camera_rotation_dir = 1
        self.last_radar_click_time = 0.0
        self.last_player_map_pos: Optional[Tuple[int, int]] = None
        self.stuck_counter = 0
        self.memorized_hotspots = [
            {"name": "Archway Turtle Field", "map_x": 0.42, "map_y": 0.65},
            {"name": "South Beach Turtle Cove", "map_x": 0.36, "map_y": 0.74},
        ]
        self.active_hotspot_idx = 0

    def navigate_or_search(
        self,
        game_state: GameState,
        minimap_dots: List[Tuple[int, int]],
        center_viewport: Tuple[int, int] = (950, 522),
    ):
        now = time.time()
        px, py = center_viewport
        screen_w = px * 2
        screen_h = py * 2

        # 1. If accurate navigation vector from minimap is available, move towards closest monster
        if game_state.minimap_vector:
            vec = game_state.minimap_vector
            current_pos = vec.player_pos

            # Track movement progress on minimap (Spatial Memory)
            if self.last_player_map_pos is not None:
                move_dist = ((current_pos[0] - self.last_player_map_pos[0]) ** 2 +
                             (current_pos[1] - self.last_player_map_pos[1]) ** 2) ** 0.5
                if move_dist < 2.0:
                    self.stuck_counter += 1
                else:
                    self.stuck_counter = 0
            self.last_player_map_pos = current_pos

            # Use 3D Isometric projected screen direction
            sx = vec.screen_dx
            sy = vec.screen_dy

            # If stuck against a mountain wall or rock on the right, divert DOWN-LEFT towards the open grass field
            if self.stuck_counter >= 2:
                print(f"[Field Nav] Wall/Rock detected (stuck {self.stuck_counter}x) -> Diverting DOWN-LEFT into open grass field!", flush=True)
                sx, sy = -0.78, 0.58

                if self.stuck_counter >= 4:
                    self.controller.press("4", delay=0.1)  # Jump forward across barrier
                    self.stuck_counter = 0

            # Walk distance in 3D screen space
            walk_dist = 240
            raw_ground_x = int(px + sx * walk_dist)
            raw_ground_y = int(py + sy * walk_dist)
            ground_x, ground_y = sanitize_combat_coordinates(raw_ground_x, raw_ground_y, screen_w, screen_h)

            print(
                f"[Field Nav] Moving towards monster cluster ({vec.total_mobs} mobs on radar, "
                f"screen_dir: ({sx:.2f}, {sy:.2f})) at ground ({ground_x}, {ground_y})...",
                flush=True,
            )

            # Double-click ground to walk
            self.controller.dblclick(ground_x, ground_y)

            # Auxiliary WASD directional nudge for responsive movement
            if sy < -0.30:
                self.controller.press("w", delay=0.08)
            elif sy > 0.30:
                self.controller.press("s", delay=0.08)

            if sx < -0.30:
                self.controller.press("a", delay=0.08)
            elif sx > 0.30:
                self.controller.press("d", delay=0.08)

            self.last_radar_click_time = now
            time.sleep(0.4)
            return

        # 2. No monsters visible on screen -> Advance DOWN-LEFT towards the open valley and sweep camera
        sweep_dx = 200 * self.camera_rotation_dir
        print(f"[Field Nav] Advancing DOWN-LEFT along the valley field & sweeping camera by {sweep_dx}px...", flush=True)
        down_x = max(150, int(px * 0.75))
        down_y = min(screen_h - 150, py + 220)
        self.controller.dblclick(down_x, down_y)
        self.controller.press("s", delay=0.25)
        self.controller.press("a", delay=0.20)
        self.controller.move(px, py)
        self.controller.drag_relative(sweep_dx, 0, button="right")
        self.camera_rotation_dir *= -1
        time.sleep(0.5)
