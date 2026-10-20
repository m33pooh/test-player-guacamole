import time
from typing import Dict, Optional, Tuple

from app.agent.policy import (
    AgentPolicyEngine,
    SKILL_3_VORTEX_DURATION,
    SKILL_1_AOE_COOLDOWN,
    SKILL_Y_SNIPER_COOLDOWN,
    SKILL_T_NOVA_COOLDOWN,
    SKILL_E_MARK_COOLDOWN,
    SKILL_Q_RAPID_COOLDOWN,
    SKILL_4_DODGE_COOLDOWN,
)
from app.controller.controller import ActionController
from app.vision.state import GameState


def sanitize_combat_coordinates(x: int, y: int, screen_w: int = 1920, screen_h: int = 1080) -> Tuple[int, int]:
    """
    Filters and clamps combat click/aim coordinates to prevent accidental clicks on UI elements.
    UI Exclusion Zones:
    1. Top-Left HUD (Player Profile, HP/MP Bar, Buffs): x < 25%, y < 16%
    2. Top-Right HUD (Minimap Radar, Channel, Bag/Menu): x > 75%, y < 28%
    3. Bottom-Center Hotbar (Skills 1-6, Q, E, R, T, Y, EXP Bar): 18% <= x <= 82%, y > 83%
    4. Bottom-Left Chat Box (Chat Window, Tabs, Input Box): x < 28%, y > 72%
    5. Right-Side Quest Tracker (Quest objectives, Auto-nav buttons): x > 82%, 25% <= y <= 78%
    6. Top-Center Boss Bar (Boss Name, Target Health): 35% <= x <= 65%, y < 10%
    """
    safe_min_x = int(screen_w * 0.16)
    safe_max_x = int(screen_w * 0.82)
    safe_min_y = int(screen_h * 0.16)
    safe_max_y = int(screen_h * 0.82)

    cx = max(safe_min_x, min(safe_max_x, x))
    cy = max(safe_min_y, min(safe_max_y, y))

    # Bottom-Left Chatbox Exclusion
    if cx < int(screen_w * 0.28) and cy > int(screen_h * 0.72):
        cx = int(screen_w * 0.30)
        cy = int(screen_h * 0.70)

    # Top-Right Minimap Exclusion
    if cx > int(screen_w * 0.75) and cy < int(screen_h * 0.28):
        cx = int(screen_w * 0.74)
        cy = int(screen_h * 0.30)

    return cx, cy


class CombatStateHandler:
    """
    Center-Anchored Trap & Relentless AoE Bomb Stacking Combat Engine:
    1. Player Character Position is ALWAYS at Screen Center: px = w // 2, py = h // 2.
    2. Skill 3 (Vortex Pull 9.0s): Dropped directly at center screen (px, py) on character's feet.
    3. Skill 1 (AoE Bomb 2.1s): NEVER FORGOTTEN. Checked and stacked at center screen (px, py)
       before and after EVERY single action!
    4. Orbital Dodge (Skill 4): Dodges around the center trap when mobs crowd.
    5. Distant Aggro: Aims long-range shots (Y sniper, E mark, Q gunshot) at distant target (tx, ty)
       to lure mobs into the center-screen death trap!
    """
    def __init__(self, controller: ActionController, policy: AgentPolicyEngine):
        self.controller = controller
        self.policy = policy
        self.last_cast: Dict[str, float] = {}
        self.last_vortex_time: float = 0.0
        self.last_dodge_time: float = 0.0
        self.prev_enemy_count: int = 0
        self.in_combat_engagement: bool = False
        self.dodge_direction: int = 1
        self.active_trap_pos: Optional[Tuple[int, int]] = None
        self.active_trap_time: float = 0.0
        self.last_target_pos: Optional[Tuple[int, int]] = None
        self.last_target_seen_time: float = 0.0

    def is_aoe_trap_active(self) -> bool:
        """Returns True if Skill 1 bomb or Skill 3 vortex is actively ticking on the ground."""
        return (time.time() - self.active_trap_time < 3.2)

    def cast_skill_1_on_cooldown(self, px: int, py: int) -> bool:
        """
        Forces Skill 1 (AoE Bomb) to be cast on cooldown (2.1s) directly at player's feet (center screen).
        """
        now = time.time()
        if (now - self.last_cast.get("1", 0) >= SKILL_1_AOE_COOLDOWN) or ("1" not in self.last_cast):
            print(f"[Combat AoE] Stacking Skill 1 (AoE Bomb) at center feet ({px}, {py})...", flush=True)
            self.controller.move(px, py)
            self.controller.press("1", delay=0.04)
            self.controller.click(px, py)
            self.last_cast["1"] = time.time()
            self.active_trap_pos = (px, py)
            self.active_trap_time = time.time()
            return True
        return False

    def execute_combat_cycle(
        self,
        game_state: GameState,
        player_pos: Tuple[int, int] = (853, 466),
    ) -> bool:
        """
        Executes one high-precision center-anchored combat burst with spatial target memory.
        """
        now = time.time()
        # Player position is ALWAYS screen center
        px, py = player_pos
        screen_w = px * 2
        screen_h = py * 2

        # 1. Distant monster targeting coordinates (Screen Spatial Memory)
        if game_state.target_pos:
            self.last_target_pos = game_state.target_pos
            self.last_target_seen_time = now
            raw_aim = game_state.target_pos
        elif self.last_target_pos and (now - self.last_target_seen_time < 3.0):
            raw_aim = self.last_target_pos
        else:
            raw_aim = (int(px * 0.75), int(py + 120))  # Down-Left valley road

        tx, ty = sanitize_combat_coordinates(raw_aim[0], raw_aim[1], screen_w, screen_h)

        dx = tx - px
        dy = ty - py
        dist = max(1.0, (dx ** 2 + dy ** 2) ** 0.5)
        nx = dx / dist
        ny = dy / dist

        # Intercepting trap position in front of player along incoming monster path
        trap_dist = max(60, min(140, int(dist * 0.55)))
        raw_vortex_x = int(px + nx * trap_dist)
        raw_vortex_y = int(py + ny * trap_dist)
        vortex_x, vortex_y = sanitize_combat_coordinates(raw_vortex_x, raw_vortex_y, screen_w, screen_h)

        # ---------------------------------------------------------------------
        # 1. TOP PRIORITY: Skill 3 (Vortex Pull - Cast in front along monster approach path)
        # ---------------------------------------------------------------------
        if (now - self.last_vortex_time >= SKILL_3_VORTEX_DURATION) or ("3" not in self.last_cast):
            print(f"[Combat Vortex Trap] Placing Skill 3 (Vortex Pull) in front of player along monster path at ({vortex_x}, {vortex_y})...", flush=True)
            self.controller.move(vortex_x, vortex_y)
            self.controller.press("3", delay=0.04)
            self.controller.click(vortex_x, vortex_y)
            self.last_vortex_time = time.time()
            self.last_cast["3"] = self.last_vortex_time
            self.active_trap_pos = (vortex_x, vortex_y)
            self.active_trap_time = time.time()
            time.sleep(0.04)

        # ---------------------------------------------------------------------
        # 2. IMMEDIATE SKILL 1 CHECK (AoE Bomb stacked directly into Vortex path)
        # ---------------------------------------------------------------------
        self.cast_skill_1_on_cooldown(px, py)

        # ---------------------------------------------------------------------
        # 3. HP Safety Check (Heal Potion '5')
        # ---------------------------------------------------------------------
        if game_state.character_hp < 0.65:
            potion_key = self.policy.get_potion_key()
            self.controller.press(potion_key, delay=0.03)
            if game_state.character_hp < 0.35:
                self.controller.press(potion_key, delay=0.03)

        # ---------------------------------------------------------------------
        # 4. Buff Maintenance (Key '6' every 20s)
        # ---------------------------------------------------------------------
        if now - self.last_cast.get("buff", 0) > 20.0:
            self.controller.press(self.policy.get_buff_key(), delay=0.03)
            self.last_cast["buff"] = now

        # ---------------------------------------------------------------------
        # 5. [EMERGENCY ESCAPE ONLY] (Skill 4: Only jump if HP is critically low <35% and mobs are swarming)
        # ---------------------------------------------------------------------
        should_dodge = (
            game_state.character_hp < 0.35
            and dist < 85
            and (now - self.last_dodge_time >= SKILL_4_DODGE_COOLDOWN)
        )
        if should_dodge:
            # Emergency Leap away across monsters
            jump_dist = 170
            raw_jump_x = int(px + nx * jump_dist)
            raw_jump_y = int(py + ny * jump_dist)
            jump_x, jump_y = sanitize_combat_coordinates(raw_jump_x, raw_jump_y, screen_w, screen_h)

            print(f"[Combat Emergency Escape] Low HP ({game_state.character_hp*100:.1f}%) -> Leaping with Skill 4 to ({jump_x}, {jump_y})...", flush=True)
            self.controller.move(jump_x, jump_y)
            self.controller.press("4", delay=0.08)
            self.last_dodge_time = now
            time.sleep(0.18)

            # Character is now on the other side! Drop Skill 3 in front towards pursuing monsters + Skill 1 Bomb
            rev_trap_x = int(px - nx * 80)
            rev_trap_y = int(py - ny * 80)
            rt_x, rt_y = sanitize_combat_coordinates(rev_trap_x, rev_trap_y, screen_w, screen_h)
            print(f"[Combat Trap Lure] Landed! Dropping Skill 3 Vortex in path ({rt_x}, {rt_y}) + Skill 1 Bomb at feet ({px}, {py})...", flush=True)
            self.controller.move(rt_x, rt_y)
            self.controller.press("3", delay=0.04)
            self.controller.click(rt_x, rt_y)
            self.last_vortex_time = time.time()
            self.last_cast["3"] = self.last_vortex_time
            self.active_trap_pos = (rt_x, rt_y)
            self.active_trap_time = time.time()
            time.sleep(0.04)
            self.cast_skill_1_on_cooldown(px, py)

        self.prev_enemy_count = game_state.enemy_count

        # ---------------------------------------------------------------------
        # 6. [SNIPER & CROWD BURST] Skill Y -> Triple Skill T (Y -> T -> T -> T)
        # ---------------------------------------------------------------------
        # If crowded (>= 3 mobs or close mob) and Y is off cooldown:
        is_crowded = (game_state.enemy_count >= 3 or dist <= 95)
        if (now - self.last_cast.get("y", 0) >= SKILL_Y_SNIPER_COOLDOWN) or ("y" not in self.last_cast):
            print(f"[Combat Sniper] Sniping target at ({tx}, {ty}) with Skill Y...", flush=True)
            self.controller.move(tx, ty)
            self.controller.press("y", delay=0.06)
            self.controller.click(tx, ty)
            self.last_cast["y"] = time.time()

            # Wait for Skill Y shooting animation lock (0.30s)
            time.sleep(0.30)

            # Triple Skill T Nova Burst (Y -> T -> T -> T) to annihilate surrounding mobs
            print(f"[Combat Nova Burst] Mobs crowded ({game_state.enemy_count} mobs) -> Executing Triple Nova: T -> T -> T...", flush=True)
            self.controller.press("t", delay=0.06)
            self.controller.click(tx, ty)
            time.sleep(0.08)
            self.controller.press("t", delay=0.06)
            time.sleep(0.08)
            self.controller.press("t", delay=0.06)
            self.last_cast["t"] = time.time()

            # Immediately stack Skill 1 AoE Bomb right after triple T
            self.cast_skill_1_on_cooldown(px, py)

        # ---------------------------------------------------------------------
        # 7. Big Monster Priority: Skill E (Hunter's Mark) Aimed at Target
        # ---------------------------------------------------------------------
        if game_state.target_is_big:
            if (now - self.last_cast.get("e", 0) >= SKILL_E_MARK_COOLDOWN) or ("e" not in self.last_cast):
                print(f"[Combat Sniper] Big Monster! Marking target at ({tx}, {ty}) with Skill E...", flush=True)
                self.controller.move(tx, ty)
                self.controller.press("e", delay=0.04)
                self.controller.click(tx, ty)
                self.last_cast["e"] = time.time()

        # ---------------------------------------------------------------------
        # 8. [RAPID PULL] Skill Q (Continuous Gunshot to Lure Mobs to Center)
        # ---------------------------------------------------------------------
        if (now - self.last_cast.get("q", 0) >= SKILL_Q_RAPID_COOLDOWN) or ("q" not in self.last_cast):
            self.controller.move(tx, ty)
            self.controller.press("q", delay=0.03)
            self.controller.click(tx, ty)
            self.last_cast["q"] = time.time()

        # ---------------------------------------------------------------------
        # 9. FINAL HEAVY SKILL 1 COOLDOWN CHECK AT END OF LOOP
        # ---------------------------------------------------------------------
        self.cast_skill_1_on_cooldown(px, py)

        return True
