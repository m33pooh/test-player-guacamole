import time
from typing import Optional, Tuple

import numpy as np

from app.agent.policy import AgentPolicyEngine
from app.controller.controller import ActionController
from app.state_machine.combat import CombatStateHandler
from app.state_machine.farming import FarmingStateHandler
from app.state_machine.recovery import RecoveryStateHandler
from app.state_machine.states import BotState
from app.state_machine.town import TownStateHandler
from app.vision.detector import FastVisionDetector
from app.vision.state import GameState
from app.vision.vlm import QwenVLStrategicBrain
from config.settings import AgentConfig


class BotStateMachine:
    """
    Finite State Machine orchestrator for MMORPG Farming Agent.
    Coordinates state transitions between Town, Map Warp, Field Navigation, Combat, and Death Recovery.
    """
    def __init__(
        self,
        controller: ActionController,
        policy: AgentPolicyEngine,
        detector: FastVisionDetector,
        vlm: QwenVLStrategicBrain,
        config: Optional[AgentConfig] = None,
    ):
        self.controller = controller
        self.policy = policy
        self.detector = detector
        self.vlm = vlm
        self.config = config or AgentConfig()

        self.current_state = BotState.UNKNOWN
        self.previous_state = BotState.UNKNOWN
        self.state_enter_time = time.time()
        self.loop_count = 0
        self.last_combat_enemy_time: float = 0.0
        self.llm_healer_pos: Optional[Tuple[int, int]] = None
        self.llm_crystal_pos: Optional[Tuple[int, int]] = None

        # Sub-handlers
        self.combat_handler = CombatStateHandler(self.controller, self.policy)
        self.farming_handler = FarmingStateHandler(self.controller)
        self.town_handler = TownStateHandler(self.controller, self.config.coords, self.detector, self.vlm)
        self.recovery_handler = RecoveryStateHandler(self.controller, self.config.coords)

    def transition_to(self, new_state: BotState):
        if self.current_state != new_state:
            self.previous_state = self.current_state
            self.current_state = new_state
            self.state_enter_time = time.time()

    def perform_initial_llm_check(self, frame: np.ndarray) -> BotState:
        """
        MANDATORY STARTUP STEP:
        Queries the LLM / VLM brain first to identify:
        1. Where is the player currently located?
        2. What is the recommended strategy (fight, warp, heal)?
        3. If in Town: exact coordinates of Healer NPC and Teleport Crystal.
        """
        print("\n" + "=" * 60, flush=True)
        print(" [LLM Initial Scene Analysis] Querying AI Brain on Startup...", flush=True)
        print("=" * 60, flush=True)
        self.update_state_via_vlm(frame)
        print(f"[LLM Initial Check] Initial State set to: {self.current_state.name}\n", flush=True)
        return self.current_state

    def update_state_via_vlm(self, frame: np.ndarray):
        """
        Uses LLM / VLM to determine:
        1. Where is the player currently located?
        2. Should we fight monsters or travel/warp?
        3. If in Town: where is the Healer NPC and where is the Teleport Crystal?
        """
        if frame is None or frame.size == 0:
            return

        res = self.vlm.query_initial_strategic_guidance(frame)
        loc = str(res.get("location", "")).lower()
        act = str(res.get("recommended_action", "")).lower()
        reasoning = res.get("reasoning", "")

        # Extract LLM Town Coordinates
        if res.get("healer_npc_x") and res.get("healer_npc_y"):
            self.llm_healer_pos = (int(res["healer_npc_x"]), int(res["healer_npc_y"]))
        if res.get("warp_crystal_x") and res.get("warp_crystal_y"):
            self.llm_crystal_pos = (int(res["warp_crystal_x"]), int(res["warp_crystal_y"]))

        # If in town and coords missing, do targeted town query
        if ("town" in loc or "heal" in act or self.detector.check_is_in_town(frame)) and (not self.llm_healer_pos or not self.llm_crystal_pos):
            town_res = self.vlm.query_town_healer_and_crystal(frame)
            if town_res.get("healer_visible") and town_res.get("healer_x") and town_res.get("healer_y"):
                self.llm_healer_pos = (int(town_res["healer_x"]), int(town_res["healer_y"]))
            if town_res.get("crystal_visible") and town_res.get("crystal_x") and town_res.get("crystal_y"):
                self.llm_crystal_pos = (int(town_res["crystal_x"]), int(town_res["crystal_y"]))

        print(f"[LLM Strategic Guidance] Location: {res.get('location', 'Unknown')} | Action: {act} | Reason: {reasoning}", flush=True)
        if self.llm_healer_pos or self.llm_crystal_pos:
            print(f"[LLM Town Navigation] Healer NPC: {self.llm_healer_pos} | Warp Crystal: {self.llm_crystal_pos}", flush=True)

        if "dead" in loc or "respawn" in act:
            self.transition_to(BotState.DEAD)
        elif "worldmap" in loc or "open_map" in act or res.get("world_map_open"):
            self.transition_to(BotState.WARP)
        elif "town" in loc or "heal_in_town" in act or self.detector.check_is_in_town(frame):
            self.transition_to(BotState.IN_TOWN)
        elif "combat" in loc or "fight" in act or len(self.detector.find_onscreen_enemies(frame)) > 0:
            self.transition_to(BotState.COMBAT)
        elif "field" in loc:
            self.transition_to(BotState.IN_FIELD)
        else:
            # CV heuristic fallback
            if self.detector.find_onscreen_enemies(frame):
                self.transition_to(BotState.COMBAT)
            elif self.detector.check_is_in_town(frame):
                self.transition_to(BotState.IN_TOWN)
            else:
                self.transition_to(BotState.IN_FIELD)

    def step(self, frame: np.ndarray, game_state: Optional[GameState] = None) -> BotState:
        """
        Executes one FSM iteration cycle.
        """
        self.loop_count += 1
        state = game_state or self.detector.parse_game_state(frame)

        # Immediate Death Check overrides all other states
        if state.dead or self.current_state == BotState.DEAD:
            self.transition_to(BotState.DEAD)
            revive_coords = self.detector.get_revive_button_coords(frame)
            frame_shape = frame.shape if frame is not None else None
            self.recovery_handler.handle_death_respawn(revive_coords, frame_shape=frame_shape)

            # Immediately execute complete Town heal & crystal warp sequence
            self.transition_to(BotState.IN_TOWN)
            fresh_town_frame = self.controller.capture_frame() if hasattr(self.controller, "capture_frame") else frame
            self.town_handler.execute_town_cycle(frame=fresh_town_frame)
            self.transition_to(BotState.IN_FIELD)
            return self.current_state

        # UNKNOWN State (or initial loop): Ask LLM where we are and what to do
        if self.current_state == BotState.UNKNOWN or (self.loop_count % 35 == 0 and self.current_state not in [BotState.COMBAT, BotState.IN_TOWN]):
            self.update_state_via_vlm(frame)
            return self.current_state

        # IN_TOWN State
        if self.current_state == BotState.IN_TOWN:
            self.town_handler.execute_town_cycle(frame=frame)
            self.transition_to(BotState.IN_FIELD)
            return self.current_state

        # Compute dynamic player center viewport based on active frame resolution
        if frame is not None and frame.size > 0:
            h, w = frame.shape[:2]
            center_viewport = (w // 2, h // 2)
        else:
            center_viewport = self.config.coords.center_viewport

        # IN_FIELD State
        if self.current_state == BotState.IN_FIELD:
            minimap_dots = self.detector.get_minimap_red_dots(frame) if frame is not None else []
            has_nearby_radar_mobs = False
            if state.minimap_vector:
                has_nearby_radar_mobs = (state.minimap_vector.distance <= 32.0 or state.minimap_vector.total_mobs >= 3)

            if state.enemy_count > 0 or state.active_target or self.combat_handler.is_aoe_trap_active() or has_nearby_radar_mobs:
                if has_nearby_radar_mobs and state.minimap_vector:
                    print(f"[FSM Combat] Monsters swarming on radar ({state.minimap_vector.total_mobs} mobs nearby) -> Entering COMBAT to blast enemies!", flush=True)
                self.last_combat_enemy_time = time.time()
                self.transition_to(BotState.COMBAT)
                return self.current_state

            self.farming_handler.navigate_or_search(state, minimap_dots, center_viewport)
            return self.current_state

        # COMBAT State
        if self.current_state == BotState.COMBAT:
            now = time.time()
            if state.enemy_count > 0 or state.active_target:
                self.last_combat_enemy_time = now

            trap_active = self.combat_handler.is_aoe_trap_active()
            no_enemies_recently = (now - self.last_combat_enemy_time > 2.2)

            if state.enemy_count == 0 and not state.active_target and no_enemies_recently and not trap_active:
                print("[FSM Combat] All enemies cleared and AoE trap expired -> Transitioning to IN_FIELD navigation...", flush=True)
                self.transition_to(BotState.IN_FIELD)
                return self.current_state

            # Hold position around active AoE trap and pull incoming monsters
            self.combat_handler.execute_combat_cycle(state, center_viewport)
            return self.current_state

        return self.current_state
