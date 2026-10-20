import time
import math

class TargetMemoryTracker:
    """
    On-Screen Monster Target Locator & Tracking Memory System.
    Maintains persistent target lock, calculates cluster centroids for AoE skills,
    and provides accurate aiming coordinates before each skill cast.
    """
    def __init__(self, lock_timeout=3.5, cluster_radius=120):
        self.lock_timeout = lock_timeout
        self.cluster_radius = cluster_radius
        self.active_target = None
        self.combo_in_progress = False
        self.lock_start_time = 0
        self.last_update_time = 0
        self.target_history = []

    def select_best_target(self, detected_enemies, player_pos=(960, 480), prefer_cluster=True):
        """
        Locates the best target on screen:
        1. If prefer_cluster is True (for AoE skills like 3 Pull / 1 AoE), finds the centroid of the densest monster cluster.
        2. Otherwise, selects the closest monster to the player character.
        """
        if not detected_enemies:
            return None

        # Clean coordinates and apply boundary clamping
        valid_mobs = []
        for mob in detected_enemies:
            raw_x, raw_y = mob[:2]
            cx = max(100, min(1500, int(raw_x)))
            cy = max(150, min(800, int(raw_y)))
            valid_mobs.append((cx, cy))

        if not valid_mobs:
            return None

        # AoE Cluster Centroid Calculation
        if prefer_cluster and len(valid_mobs) > 1:
            best_cluster_center = None
            max_cluster_size = 0
            best_dist_to_player = float('inf')

            for ref_x, ref_y in valid_mobs:
                # Find all mobs within cluster radius
                cluster_members = [
                    (mx, my) for mx, my in valid_mobs
                    if math.hypot(mx - ref_x, my - ref_y) <= self.cluster_radius
                ]
                cluster_size = len(cluster_members)
                avg_x = int(sum(m[0] for m in cluster_members) / cluster_size)
                avg_y = int(sum(m[1] for m in cluster_members) / cluster_size)
                dist_to_player = math.hypot(avg_x - player_pos[0], avg_y - player_pos[1])

                if cluster_size > max_cluster_size or (cluster_size == max_cluster_size and dist_to_player < best_dist_to_player):
                    max_cluster_size = cluster_size
                    best_cluster_center = (avg_x, avg_y)
                    best_dist_to_player = dist_to_player

            if max_cluster_size >= 2 and best_cluster_center:
                return {
                    "x": best_cluster_center[0],
                    "y": best_cluster_center[1],
                    "type": "cluster",
                    "mob_count": max_cluster_size
                }

        # Single Nearest Target
        closest_mob = min(
            valid_mobs,
            key=lambda pt: math.hypot(pt[0] - player_pos[0], pt[1] - player_pos[1])
        )
        return {
            "x": closest_mob[0],
            "y": closest_mob[1],
            "type": "single",
            "mob_count": 1
        }

    def update_or_acquire_target(self, detected_enemies, player_pos=(960, 480)):
        """
        Updates the current target memory:
        - If already locked onto an active target and combo is in progress, matches nearest detected enemy to maintain lock.
        - If current target has timed out or no target locked, acquires the best new target.
        """
        now = time.time()

        # Check if current lock has expired (only if no enemies detected at all for a long duration)
        if self.active_target and not detected_enemies and (now - self.last_update_time > self.lock_timeout):
            print(f"[Target Tracker] Target defeated or lost at ({self.active_target['x']}, {self.active_target['y']}).")
            self.clear_target()

        if detected_enemies:
            if self.active_target:
                # Maintain sticky lock on the existing target until eliminated
                cur_x, cur_y = self.active_target["x"], self.active_target["y"]
                closest_to_lock = min(
                    detected_enemies,
                    key=lambda pt: math.hypot(pt[0] - cur_x, pt[1] - cur_y)
                )
                dist = math.hypot(closest_to_lock[0] - cur_x, closest_to_lock[1] - cur_y)

                # Track position updates
                if dist <= 280:
                    smooth_x = int(0.5 * cur_x + 0.5 * closest_to_lock[0])
                    smooth_y = int(0.5 * cur_y + 0.5 * closest_to_lock[1])
                    self.active_target["x"] = max(100, min(1500, smooth_x))
                    self.active_target["y"] = max(150, min(800, smooth_y))
                    self.last_update_time = now
                    return self.active_target
                else:
                    # Switch to closest enemy if old target was killed
                    new_target = self.select_best_target(detected_enemies, player_pos=player_pos)
                    if new_target:
                        self.active_target = new_target
                        self.last_update_time = now
                        self.combo_in_progress = True
                        return self.active_target

            # No existing target: acquire best target
            new_target = self.select_best_target(detected_enemies, player_pos=player_pos)
            if new_target:
                self.active_target = new_target
                self.lock_start_time = now
                self.last_update_time = now
                self.combo_in_progress = True
                print(f"[Target Tracker] Acquired sticky target at ({new_target['x']}, {new_target['y']}) | Mode: {new_target['type']}")
                return self.active_target

        return self.active_target

    def get_aim_coordinates(self):
        """Returns the current target coordinates (x, y) for skill aiming"""
        if self.active_target:
            return (self.active_target["x"], self.active_target["y"])
        return None

    def clear_target(self):
        """Clears active target upon kill or timeout"""
        self.active_target = None
        self.combo_in_progress = False
        self.lock_start_time = 0
        self.last_update_time = 0
