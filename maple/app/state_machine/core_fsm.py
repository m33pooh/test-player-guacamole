import time
from enum import Enum
from typing import Dict, Any, Optional
import numpy as np

from maple.app.controller.input_driver import GuacamoleInputDriver
from maple.app.state_machine.rotation_farm import RotationFarmEngine
from maple.app.state_machine.rune_state import RuneSolvingEngine
from maple.app.state_machine.channel_surfer import ChannelSurfer
from maple.app.agent.memory_db import MemoryDB
from maple.app.agent.buff_synchronizer import BuffSynchronizer


class MapleState(str, Enum):
    ROTATION_FARM = "ROTATION_FARM"
    RUNE_SOLVING = "RUNE_SOLVING"
    EMERGENCY_HEAL = "EMERGENCY_HEAL"
    CHANGE_CHANNEL = "CHANGE_CHANNEL"
    DEAD_RECOVERY = "DEAD_RECOVERY"
    SECURITY_ALERT = "SECURITY_ALERT"
    ELITE_COMBAT = "ELITE_COMBAT"


class MapleStateMachine:
    """
    Core Reactive Finite State Machine for MapleStory Farming Agent.
    Prioritizes security/GM alerts -> Death -> Low HP -> Anti-KS Channel Hop -> Rune Solving -> Map Rotation.
    """

    def __init__(
        self,
        driver: GuacamoleInputDriver,
        rotation_engine: RotationFarmEngine,
        rune_engine: RuneSolvingEngine,
        channel_surfer: ChannelSurfer,
        memory_db: MemoryDB,
        potion_key: str = "PageDown",
        buff_sync: Optional[BuffSynchronizer] = None,
    ):
        self.driver = driver
        self.rotation_engine = rotation_engine
        self.rune_engine = rune_engine
        self.channel_surfer = channel_surfer
        self.memory_db = memory_db
        self.potion_key = potion_key
        self.buff_sync = buff_sync or BuffSynchronizer()

        self.current_state = MapleState.ROTATION_FARM
        self.last_potion_time = 0.0
        self.prev_exp = 0.0
        self.state_enter_time = time.time()

    def update(
        self,
        frame: np.ndarray,
        minimap_state: Dict[str, Any],
        status_state: Dict[str, Any],
        mob_state: Dict[str, Any],
        security_state: Dict[str, Any],
        class_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = time.time()
        player_pos = minimap_state.get("player_pos")
        rune_pos = minimap_state.get("rune_pos")
        other_players_count = minimap_state.get("other_players_count", 0)

        hp_ratio = status_state.get("hp_ratio", 1.0)
        mp_ratio = status_state.get("mp_ratio", 1.0)
        is_dead = status_state.get("is_dead", False)
        elite_present = mob_state.get("elite_present", False)

        # 1. Security / Anti-Bot Alert Check
        if security_state.get("captcha_detected") or security_state.get("white_room"):
            self.current_state = MapleState.SECURITY_ALERT
            print("[CoreFSM ALERT] Security / White Room detected! Pausing automation...", flush=True)
            self.memory_db.record_telemetry(
                self.current_state.value, "PAUSE_ALERT", player_pos, hp_ratio, mp_ratio, self.channel_surfer.current_channel
            )
            time.sleep(1.0)
            return {"state": self.current_state.value, "action": "PAUSED_FOR_SECURITY"}

        # 2. Death Check
        if is_dead:
            self.current_state = MapleState.DEAD_RECOVERY
            print("[CoreFSM] Player is DEAD! Pressing Enter to respawn...", flush=True)
            self.driver.press_key("Enter")
            time.sleep(2.0)
            return {"state": self.current_state.value, "action": "RESPAWN"}

        # 3. Emergency HP Recovery (Non-blocking instant key tap)
        if hp_ratio < 0.50 and (now - self.last_potion_time) > 0.5:
            print(f"[CoreFSM] Low HP ({hp_ratio*100:.0f}%)! Pressing potion ({self.potion_key})...", flush=True)
            self.driver.tap_key(self.potion_key)
            self.last_potion_time = now

        # 4. Anti-KS / Channel Surfing Check
        if self.channel_surfer.update_other_players(other_players_count):
            self.current_state = MapleState.CHANGE_CHANNEL
            self.channel_surfer.execute_channel_change()
            self.memory_db.record_channel_change()
            self.current_state = MapleState.ROTATION_FARM
            return {"state": MapleState.CHANGE_CHANNEL.value, "action": "CHANNEL_CHANGED"}

        # 5. Rune Solving State Transition
        if self.current_state == MapleState.RUNE_SOLVING:
            if not rune_pos:
                # Rune disappeared or solved
                self.current_state = MapleState.ROTATION_FARM
            else:
                t_start = time.time()
                res = self.rune_engine.step(player_pos, rune_pos, frame)
                if res.get("status") == "SUCCESS":
                    self.memory_db.record_rune_event(
                        duration=time.time() - t_start,
                        success=True,
                        arrows=res.get("arrows", []),
                    )
                    self.current_state = MapleState.ROTATION_FARM
                elif res.get("status") == "FAILED":
                    self.memory_db.record_rune_event(duration=4.0, success=False, arrows=[])
                    self.current_state = MapleState.ROTATION_FARM
                return {"state": MapleState.RUNE_SOLVING.value, "action": res.get("phase", "SOLVING")}

        # Check if new Rune appeared and can be solved
        if rune_pos and self.rune_engine.can_solve_rune():
            if not self.buff_sync.should_delay_rune_for_fma():
                print(f"[CoreFSM] Rune detected at {rune_pos}! Switching to RUNE_SOLVING...", flush=True)
                self.rune_engine.reset()
                self.current_state = MapleState.RUNE_SOLVING
                return {"state": self.current_state.value, "action": "INIT_RUNE"}

        # 6. Elite Monster Combat
        if elite_present:
            self.current_state = MapleState.ELITE_COMBAT
            print("[CoreFSM] Elite monster engaged! Triggering burst skill rotation...", flush=True)
            self.driver.press_combo(["q", "w", "e", "r"])
            return {"state": self.current_state.value, "action": "ELITE_BURST"}

        # 7. Default State: Map Rotation Farming
        self.current_state = MapleState.ROTATION_FARM
        action_str = self.rotation_engine.execute_rotation_step(player_pos, class_state=class_state)

        # Estimate kills from mob clusters cleared
        total_mobs = mob_state.get("total_mobs", 0)
        if "ATTACK" in action_str or "CAST" in action_str or "SWEEP" in action_str:
            estimated_kills = max(1, min(8, total_mobs))
            self.memory_db.record_kill(estimated_kills)

        self.memory_db.record_telemetry(
            state=self.current_state.value,
            action=action_str,
            minimap_pos=player_pos,
            hp_ratio=hp_ratio,
            mp_ratio=mp_ratio,
            channel=self.channel_surfer.current_channel,
        )

        return {"state": self.current_state.value, "action": action_str}
