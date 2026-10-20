from enum import Enum
import time
from typing import Dict, List, Optional, Any
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
    BUFF_AND_SUMMON = "BUFF_AND_SUMMON"
    CHANGE_CHANNEL = "CHANGE_CHANNEL"
    ELITE_COMBAT = "ELITE_COMBAT"
    EMERGENCY_HEAL = "EMERGENCY_HEAL"
    ALERT_RECOVERY = "ALERT_RECOVERY"


class MapleStateMachine:
    """
    Core Reactive State Machine for MapleStory AI Farming Agent.
    Orchestrates fast-path state transitions based on Minimap tracking,
    HP/MP status, Rune presence, and anti-KS security events.
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
        self.state_enter_time = time.time()
        self.last_heal_time = 0.0

    def transition_to(self, new_state: MapleState, reason: str = ""):
        if new_state != self.current_state:
            print(f"[State Machine] [{self.current_state.value}] -> [{new_state.value}] | Reason: {reason}", flush=True)
            self.current_state = new_state
            self.state_enter_time = time.time()
            if new_state == MapleState.RUNE_SOLVING:
                self.rune_engine.reset()

    def update(
        self,
        frame: np.ndarray,
        minimap_state: Dict[str, Any],
        status_state: Dict[str, Any],
        mob_state: Dict[str, Any],
        security_state: Dict[str, Any],
        class_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes one tick of the State Machine.
        """
        now = time.time()
        player_pos = minimap_state.get("player_pos")
        rune_pos = minimap_state.get("rune_pos")
        other_players_count = minimap_state.get("other_players_count", 0)

        hp_ratio = status_state.get("hp_ratio", 1.0)
        mp_ratio = status_state.get("mp_ratio", 1.0)
        is_dead = status_state.get("is_dead", False)
        elite_present = mob_state.get("elite_present", False)

        # -------------------------------------------------------------
        # GLOBAL INTERRUPTS & SAFETY CHECKS
        # -------------------------------------------------------------
        # 1. Security Alert
        if security_state.get("captcha_detected") or security_state.get("white_room"):
            self.transition_to(MapleState.ALERT_RECOVERY, "Security / Verification dialog active")

        # 2. Emergency Heal
        if hp_ratio < 0.35 and (now - self.last_heal_time) > 0.8:
            print(f"[Emergency Heal] HP at {hp_ratio*100:.0f}%, consuming potion ({self.potion_key})...", flush=True)
            self.driver.press_key(self.potion_key)
            self.last_heal_time = now
            self.memory_db.record_telemetry(
                state=self.current_state.value,
                action="EMERGENCY_HEAL",
                minimap_pos=player_pos,
                hp_ratio=hp_ratio,
                mp_ratio=mp_ratio,
            )

        # 3. Anti-KS Channel Surfing Trigger
        if self.current_state != MapleState.CHANGE_CHANNEL:
            should_cc = self.channel_surfer.update_other_players(other_players_count)
            if should_cc:
                self.transition_to(MapleState.CHANGE_CHANNEL, "Other player lingering in map")

        # -------------------------------------------------------------
        # STATE LOGIC EXECUTION
        # -------------------------------------------------------------
        action_result = "IDLE"

        # STATE: ROTATION_FARM
        if self.current_state == MapleState.ROTATION_FARM:
            # Check Rune trigger
            if rune_pos and self.rune_engine.can_solve_rune():
                if self.buff_sync.should_delay_rune_for_fma():
                    # Delay brief moment to sync with FMA burst
                    action_result = self.rotation_engine.execute_rotation_step(player_pos, class_state)
                else:
                    self.transition_to(MapleState.RUNE_SOLVING, "Rune detected on minimap")
            elif elite_present:
                self.transition_to(MapleState.ELITE_COMBAT, "Elite monster detected")
            else:
                action_result = self.rotation_engine.execute_rotation_step(player_pos, class_state)

        # STATE: RUNE_SOLVING
        elif self.current_state == MapleState.RUNE_SOLVING:
            res = self.rune_engine.step(player_pos, rune_pos, frame)
            action_result = f"RUNE_{res.get('status')}_{res.get('phase', '')}"
            if res.get("status") in ["SUCCESS", "FAILED"]:
                self.memory_db.record_rune_event(
                    duration=now - self.state_enter_time,
                    success=(res.get("status") == "SUCCESS"),
                    arrows=res.get("arrows", []),
                )
                self.transition_to(MapleState.ROTATION_FARM, f"Rune phase concluded ({res.get('status')})")

        # STATE: CHANGE_CHANNEL
        elif self.current_state == MapleState.CHANGE_CHANNEL:
            self.channel_surfer.execute_channel_change()
            self.memory_db.record_channel_change()
            self.transition_to(MapleState.ROTATION_FARM, "Channel change complete")

        # STATE: ELITE_COMBAT
        elif self.current_state == MapleState.ELITE_COMBAT:
            # Cast burst skills and attacks
            print("[Elite Combat] Engaging Elite Boss with burst skills...", flush=True)
            self.driver.press_combo(["q", "w", "e", "r"])
            action_result = "BURST_ATTACK"
            if not elite_present:
                self.transition_to(MapleState.ROTATION_FARM, "Elite boss defeated")

        # STATE: ALERT_RECOVERY
        elif self.current_state == MapleState.ALERT_RECOVERY:
            print("[ALERT RECOVERY] AI paused due to security alert. Awaiting resolution...", flush=True)
            time.sleep(1.0)
            action_result = "SECURITY_PAUSE"

        # Record telemetry
        self.memory_db.record_telemetry(
            state=self.current_state.value,
            action=action_result,
            minimap_pos=player_pos,
            hp_ratio=hp_ratio,
            mp_ratio=mp_ratio,
            channel=self.channel_surfer.current_channel,
        )

        return {
            "state": self.current_state.value,
            "action": action_result,
            "time_in_state": round(now - self.state_enter_time, 2),
        }
