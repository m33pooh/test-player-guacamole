จากการตรวจสอบโค้ดทั้งหมดในโฟลเดอร์ `maple/` พบว่าโครงสร้างสถาปัตยกรรมถูกวางไว้ครบถ้วนตามที่ได้ออกแบบไว้ แต่มี **จุดที่เป็นบั๊ก (Critical Bugs)**, **ไฟล์ที่ขาดหายไปในระบบ**, และ **จุดที่โครงสร้าง YAML ไม่ตรงกับโค้ด Python** ซึ่งจะทำให้รันจริงแล้วเกิด Error หรือทำงานไม่ครบสมบูรณ์ ดังนี้ครับ:

---

## 1. รายการตรวจสอบพบปัญหา (Audit & Bug Report)

### 1.1 ไฟล์ `core_fsm.py` ขาดหายไป หรือไม่ได้ถูกรวมในแพ็กเกจ (Critical)

* **ปัญหา:** ในไฟล์ `maple/app/main.py` และ `maple/app/state_machine/__init__.py` มีการเรียกใช้ `from maple.app.state_machine.core_fsm import MapleStateMachine, MapleState` แต่ในรายการไฟล์ของโปรเจกต์ (`maple/app/state_machine/`) ไม่มีไฟล์ `core_fsm.py` ปรากฏอยู่เลย (มีเพียง `channel_surfer.py`, `loot_cycle.py`, `rotation_farm.py`, `rune_state.py`) ซึ่งจะทำให้เกิด `ModuleNotFoundError` ทันทีที่รัน `maple/app/main.py`



### 1.2 โครงสร้าง YAML ของ `buffs` ไม่ตรงกันระหว่างอาชีพ (Schema Mismatch)

* **ปัญหา:** ใน `maple/app/state_machine/rotation_farm.py` บรรทัดที่ 51 และ 76 โค้ดดึงค่าด้วย `self.buffs = class_config.get("buffs", {})` และวนลูปด้วย `for buff_name, b_info in self.buffs.items():`

* ในไฟล์ `night_lord.yaml` เขียน `buffs` ไว้เป็น **Dictionary** และอยู่ระดับ Root จึงทำงานได้ปกติ


* แต่ในไฟล์ `bishop.yaml`, `buccaneer.yaml`, และ `lara.yaml` กลับเขียน `buffs` ไว้เป็น **List (`- name: ...`)** และซ้อนอยู่ข้างในคีย์ `skills:` อีกชั้นหนึ่ง




* **ผลกระทบ:** เมื่อรันด้วยอาชีพ Bishop, Buccaneer หรือ Lara บอทจะไม่กดบัฟใดๆ เลย หรือถ้าดึงมาได้ก็จะเกิด `AttributeError: 'list' object has no attribute 'items'`

### 1.3 ลอจิกการเดินข้ามชั้นแพลตฟอร์ม (Vertical Navigation) ใน Archetypes ยังไม่เชื่อมกับ Pathfinder

* **ปัญหา:** ใน `ProjectileFSM`, `SummonerFSM`, และ `SweeperFSM` ตอนสั่งเดินไปยัง Waypoint โค้ดเช็คแค่ระยะห่างแนวราบ `dx = tx - px` แล้วสั่งกระโดดซ้าย/ขวาอย่างเดียว โดยไม่ได้เรียกใช้ `self.pathfinder.plan_path(px, py, tx, ty)`


* **ผลกระทบ:** เมื่อ Waypoint ถัดไปอยู่ชั้นบน (`y=60` หรือ `y=86`) หรือต้องโดดลงชั้นล่าง (`y=112`) ตัวละครจะกระโดดซ้าย-ขวาติดอยู่แค่ชั้นเดิม ไม่ยอมกด `Rope Lift` หรือ `Down + Jump` ทำให้ค้างอยู่ที่ Waypoint เดิมตลอดไป

### 1.4 ลอจิก `LootCycleEngine` วนเก็บของแค่จุดเดียว

* **ปัญหา:** ใน `maple/app/state_machine/loot_cycle.py` ฟังก์ชัน `execute_loot_sweep` ดึงค่า `target_s = self.summon_locations[0]` ตลอดเวลาโดยไม่มีการขยับ Index และใน `rotation_farm.py` ทันทีที่เก็บจุดแรกเสร็จ (`LOOTED_STATION`) ก็สั่งปิด `self.loot_engine.is_looting = False` ทันที


* **ผลกระทบ:** หากแผนที่มีจุดวาง Summon 2 จุด (เช่นใน `carcion_beach_3.yaml` ที่มีทั้ง `erda_fountain` และ `sol_janus_1`) บอทจะเดินไปเก็บเงินแค่จุดแรกจุดเดียวเสมอ ส่วนอีกจุดถุงเงินจะหายไปฟรีๆ



### 1.5 `VLMInspector` และ `SocialResponder` ถูกสร้างไว้แต่ยังไม่ได้ถูกเรียกใช้งานจริง

* **ปัญหา:** ใน `maple/app/main.py` มีการประกาศ `self.vlm_inspector = VLMInspector()` แต่ในลูปทำงานกลับตั้งค่าคงที่ไว้ว่า `security_state = {"captcha_detected": False, "white_room": False}` โดยไม่ได้เรียก `self.vlm_inspector.inspect_scene(frame)` ในช่วง Slow Path



---

## 2. โค้ดที่ปรับปรุงและเพิ่มเติมให้สมบูรณ์

คุณสามารถนำโค้ดด้านล่างไปสร้างหรือทับไฟล์เดิมในโฟลเดอร์ `maple/` ได้เลยครับ:

### 2.1 สร้างไฟล์ที่ขาดหาย: `maple/app/state_machine/core_fsm.py`

ไฟล์นี้คือหัวใจหลักที่เชื่อม `Minimap`, `Status`, `Rune`, `Rotation`, `ChannelSurfer` และ `BuffSynchronizer` เข้าด้วยกัน:

```python
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
            print("[CoreFSM] Player is DEAD! Pressing Enter/Click to respawn...", flush=True)
            self.driver.press_key("Enter")
            time.sleep(2.0)
            return {"state": self.current_state.value, "action": "RESPAWN"}

        # 3. Emergency HP & MP Recovery (Non-blocking instant key tap)
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

        # 6. Default State: Map Rotation Farming
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

```

---

### 2.2 ปรับปรุง `maple/app/state_machine/rotation_farm.py`

แก้ไขให้รองรับรูปแบบ `buffs` ทั้งแบบ Dictionary และแบบ List ใน YAML ของทุกอาชีพ รวมถึงเชื่อมต่อ **Pathfinder สำหรับการขึ้น-ลงแพลตฟอร์ม (`ROPE_LIFT` / `DOWN_JUMP`)** ก่อนส่งให้ Archetype โจมตี:

```python
import inspect
import time
from typing import Dict, List, Optional, Any
from maple.app.controller.input_driver import GuacamoleInputDriver
from maple.app.navigation.pathfinder import Pathfinder
from maple.app.navigation.movement_macros import MovementMacros
from maple.app.state_machine.loot_cycle import LootCycleEngine
from maple.app.state_machine.archetypes.teleporter_fsm import TeleporterFSM
from maple.app.state_machine.archetypes.projectile_fsm import ProjectileFSM
from maple.app.state_machine.archetypes.summoner_fsm import SummonerFSM
from maple.app.state_machine.archetypes.sweeper_fsm import SweeperFSM


class RotationFarmEngine:
    """
    Combat & Map Rotation execution engine.
    Supports unified buff parsing across YAML schemas and 2D vertical platform navigation.
    """

    def __init__(
        self,
        driver: GuacamoleInputDriver,
        pathfinder: Pathfinder,
        map_config: Dict[str, Any],
        class_config: Dict[str, Any],
    ):
        self.driver = driver
        self.pathfinder = pathfinder
        self.map_config = map_config
        self.class_config = class_config

        self.waypoints: List[Dict[str, Any]] = map_config.get("waypoints", [])
        self.current_waypoint_idx = 0

        self.macros = MovementMacros(driver)
        self.loot_engine = LootCycleEngine(driver, pathfinder, map_config)

        # Instantiate class archetype engine
        archetype = class_config.get("archetype", "PROJECTILE").upper()
        if "TELEPORT" in archetype:
            self.archetype_engine = TeleporterFSM(driver, self.macros, pathfinder, class_config, map_config)
        elif "SUMMON" in archetype or "LARA" in archetype:
            self.archetype_engine = SummonerFSM(driver, self.macros, pathfinder, class_config, map_config)
        elif "SWEEP" in archetype or "BUCCANEER" in archetype or "ADELE" in archetype:
            self.archetype_engine = SweeperFSM(driver, self.macros, pathfinder, class_config, map_config)
        else:
            self.archetype_engine = ProjectileFSM(driver, self.macros, pathfinder, class_config, map_config)

        # Normalize buffs from either root 'buffs' (dict/list) or 'skills.buffs' (list)
        self.normalized_buffs = self._parse_buffs(class_config)
        self.buff_timers: Dict[str, float] = {}

        # Extract rope lift & jump keys
        skills = class_config.get("skills", {})
        movement = class_config.get("movement", {})
        self.rope_lift_key = movement.get("rope_lift_key") or skills.get("rope_lift", "v")
        self.jump_key = movement.get("jump_key") or skills.get("jump", "Alt")

    def _parse_buffs(self, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw_buffs = cfg.get("buffs") or cfg.get("skills", {}).get("buffs", [])
        parsed = []
        if isinstance(raw_buffs, dict):
            for b_name, b_data in raw_buffs.items():
                parsed.append({
                    "name": b_name,
                    "key": b_data.get("key"),
                    "cooldown": float(b_data.get("cooldown", b_data.get("cooldown_sec", 180.0))),
                })
        elif isinstance(raw_buffs, list):
            for item in raw_buffs:
                if isinstance(item, dict):
                    parsed.append({
                        "name": item.get("name", "buff"),
                        "key": item.get("key"),
                        "cooldown": float(item.get("cooldown_sec", item.get("cooldown", 180.0))),
                    })
        return parsed

    def get_current_waypoint(self) -> Optional[Dict[str, Any]]:
        if not self.waypoints:
            return None
        return self.waypoints[self.current_waypoint_idx]

    def advance_waypoint(self):
        if self.waypoints:
            prev_idx = self.current_waypoint_idx
            self.current_waypoint_idx = (self.current_waypoint_idx + 1) % len(self.waypoints)
            if self.current_waypoint_idx == 0 and prev_idx == len(self.waypoints) - 1:
                self.loot_engine.on_waypoint_loop_completed()

    def execute_rotation_step(
        self,
        player_pos: List[int],
        class_state: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not player_pos or len(player_pos) < 2:
            return "NO_PLAYER_POS"

        px, py = player_pos[0], player_pos[1]
        now = time.time()

        # 1. Cast buffs if off cooldown
        for b in self.normalized_buffs:
            b_name = b["name"]
            b_key = b["key"]
            b_cd = b["cooldown"]
            last_t = self.buff_timers.get(b_name, 0.0)
            if b_key and (now - last_t) > b_cd:
                print(f"[RotationFarm] Casting buff {b_name} ({b_key})...", flush=True)
                self.driver.press_key(b_key)
                self.buff_timers[b_name] = now
                time.sleep(0.08)

        # 2. Check if currently in Loot Cycle (cycles 14-15)
        if self.loot_engine.is_looting:
            loot_act = self.loot_engine.execute_loot_sweep(player_pos)
            if loot_act == "ALL_STATIONS_LOOTED":
                self.loot_engine.is_looting = False
            return f"LOOT_CYCLE_{loot_act}"

        # 3. Check current waypoint distance
        wp = self.get_current_waypoint()
        if not wp:
            return "NO_WAYPOINTS"

        tx, ty = wp["x"], wp["y"]
        dist = ((tx - px) ** 2 + (ty - py) ** 2) ** 0.5

        if dist <= 12:
            print(f"[RotationFarm] Reached waypoint #{self.current_waypoint_idx+1} at ({tx}, {ty})", flush=True)
            self.advance_waypoint()
            return "WAYPOINT_REACHED"

        # 4. Vertical Platform Pathfinding Check (Rope Lift / Down+Jump)
        # If player is on a different vertical platform level (|ty - py| > 15), use Pathfinder first
        if abs(ty - py) > 15 and not isinstance(self.archetype_engine, TeleporterFSM):
            steps = self.pathfinder.plan_path(px, py, tx, ty)
            if steps:
                first_step = steps[0]
                act = first_step.get("action")
                if act == "ROPE_LIFT":
                    print(f"[RotationFarm] Ascending platform via Rope Lift ({self.rope_lift_key}) -> target Y={ty}", flush=True)
                    self.macros.rope_lift(rope_key=self.rope_lift_key)
                    time.sleep(0.6)
                    return "VERTICAL_ROPE_LIFT"
                elif act == "DOWN_JUMP":
                    print(f"[RotationFarm] Dropping down platform via Down+Jump -> target Y={ty}", flush=True)
                    self.macros.down_jump(jump_key=self.jump_key)
                    time.sleep(0.35)
                    return "VERTICAL_DOWN_JUMP"

        # 5. Delegate Horizontal Combat & Movement to Class Archetype Engine
        if hasattr(self.archetype_engine, "execute_step"):
            try:
                sig = inspect.signature(self.archetype_engine.execute_step)
                if len(sig.parameters) >= 3:
                    return self.archetype_engine.execute_step(player_pos, wp, class_state)
                else:
                    return self.archetype_engine.execute_step(player_pos, wp)
            except Exception as e:
                print(f"[RotationFarm Warning] Archetype execution exception: {e}", flush=True)

        return "ROTATION_STEP"

```

---

### 2.3 ปรับปรุง `maple/app/state_machine/loot_cycle.py`

แก้ไขให้เดินเก็บถุงเงินครบ **ทุกจุดวาง Summon** ในแผนที่ตามลำดับ (Multi-station Loot Sweep):

```python
import time
from typing import Dict, List, Any
from maple.app.controller.input_driver import GuacamoleInputDriver
from maple.app.navigation.pathfinder import Pathfinder


class LootCycleEngine:
    """
    15-Cycle Multi-Station Loot & Refresh Engine.
    Routes through ALL summon stations (Erda Fountain, Sol Janus, etc.) sequentially
    during cycles 14-15 before returning to kill-focus rotation.
    """

    def __init__(
        self,
        driver: GuacamoleInputDriver,
        pathfinder: Pathfinder,
        map_config: Dict[str, Any],
        total_cycle_count: int = 15,
        loot_cycles_start: int = 14,
    ):
        self.driver = driver
        self.pathfinder = pathfinder
        self.map_config = map_config
        self.total_cycle_count = total_cycle_count
        self.loot_cycles_start = loot_cycles_start

        self.current_cycle = 1
        self.summon_locations: List[List[int]] = []
        self.current_station_idx = 0

        summons = map_config.get("summon_positions", {})
        if isinstance(summons, dict):
            self.summon_locations = list(summons.values())
        elif isinstance(summons, list):
            self.summon_locations = summons
        else:
            default_pos = map_config.get("summon_position")
            if default_pos:
                self.summon_locations = [default_pos]

        self.is_looting = False

    def on_waypoint_loop_completed(self):
        self.current_cycle = (self.current_cycle % self.total_cycle_count) + 1
        was_looting = self.is_looting
        self.is_looting = (self.current_cycle >= self.loot_cycles_start)
        if self.is_looting and not was_looting:
            self.current_station_idx = 0
            print(
                f"[LootCycleEngine] Cycle #{self.current_cycle}/{self.total_cycle_count} "
                f"[LOOT & REFRESH PHASE ACTIVE - {len(self.summon_locations)} stations]",
                flush=True,
            )
        else:
            print(f"[LootCycleEngine] Cycle #{self.current_cycle}/{self.total_cycle_count} [KILL FOCUS PHASE]", flush=True)

    def execute_loot_sweep(self, player_pos: List[int]) -> str:
        if not player_pos or not self.summon_locations:
            return "ALL_STATIONS_LOOTED"

        if self.current_station_idx >= len(self.summon_locations):
            self.current_station_idx = 0
            return "ALL_STATIONS_LOOTED"

        px, py = player_pos[0], player_pos[1]
        target_s = self.summon_locations[self.current_station_idx]
        sx, sy = target_s[0], target_s[1]
        dist = ((px - sx) ** 2 + (py - sy) ** 2) ** 0.5

        if dist <= 10:
            print(
                f"[LootCycleEngine] Swept station #{self.current_station_idx+1} at ({sx}, {sy}). Refreshing summon...",
                flush=True,
            )
            self.driver.press_combo(["ArrowDown", "s"])
            time.sleep(0.1)
            self.current_station_idx += 1
            if self.current_station_idx >= len(self.summon_locations):
                self.current_station_idx = 0
                return "ALL_STATIONS_LOOTED"
            return f"STATION_{self.current_station_idx}_LOOTED"

        steps = self.pathfinder.plan_path(px, py, sx, sy)
        if steps:
            s = steps[0]
            act = s.get("action")
            if act == "FLASH_JUMP":
                self.driver.flash_jump(direction=s.get("direction", "right"))
            elif act == "DOWN_JUMP":
                self.driver.down_jump()
            elif act == "ROPE_LIFT":
                self.driver.rope_lift()
            else:
                self.driver.walk(direction=s.get("direction", "right"), duration=0.25)
        return f"ROUTING_TO_STATION_{self.current_station_idx+1}"

```

---

### 2.4 ปรับปรุง `maple/app/main.py` ให้เชื่อม VLM Security Check และ Dynamic Summon Optimization

อัปเดตส่วน Slow Path ใน `maple/app/main.py` (บรรทัดที่ 138-162) ให้เรียกใช้ `vlm_inspector.inspect_scene(frame)` จริง และนำตำแหน่งมอนสเตอร์ที่เหลือตกค้างไปปรับจุดวาง Summon อัตโนมัติ:

```python
                # 3. SLOW PATH: Periodic Strategic Planning & VLM Anomaly Check
                security_state = {"captcha_detected": False, "white_room": False}
                if (t0 - self.last_slow_path_time) >= self.slow_path_interval:
                    # 3.1 VLM Security & Anti-Bot Inspection
                    if not self.simulate:
                        vlm_res = self.vlm_inspector.inspect_scene(frame)
                        if isinstance(vlm_res, dict):
                            security_state["captcha_detected"] = bool(vlm_res.get("captcha_detected", False))
                            security_state["white_room"] = bool(vlm_res.get("white_room", False))

                    # 3.2 Performance & One-Shot Efficiency Check
                    metrics = self.memory_db.get_summary_metrics()
                    print(
                        f"\n[Slow Path] Session Metrics: Kills={metrics['session_kills']} | "
                        f"Kills/min={metrics['kills_per_minute']} | Runes={metrics['runes_solved']} ({metrics['rune_success_rate']}%)",
                        flush=True,
                    )

                    max_spawn = self.map_config.get("max_map_spawn_limit", 290.0)
                    one_shot_res = self.planner.evaluate_one_shot_efficiency(metrics["kills_per_minute"], max_spawn_cap=max_spawn)
                    print(
                        f"[Slow Path] One-Shot Status: {one_shot_res.get('status')} | "
                        f"Efficiency: {one_shot_res.get('efficiency_ratio')} | {one_shot_res.get('recommendation')}",
                        flush=True,
                    )

                    # 3.3 Dynamic Summon Optimization (Section 5.2)
                    clusters = mob_state.get("clusters", [])
                    if clusters and self.rotation_engine.loot_engine.summon_locations:
                        residual_coords = [[c["center_x"], c["center_y"]] for c in clusters]
                        cur_s = self.rotation_engine.loot_engine.summon_locations[0]
                        self.planner.optimize_summon_placement(residual_coords, cur_s)

                    # 3.4 LLM Rotation Evaluation
                    plan_res = self.planner.evaluate_rotation_efficiency(
                        metrics=metrics,
                        map_name=self.map_config.get("map_name", ""),
                        current_rotation="clockwise",
                    )
                    print(f"[Slow Path] Strategic Recommendation: {plan_res.get('recommendation')}\n", flush=True)
                    self.last_slow_path_time = t0

```