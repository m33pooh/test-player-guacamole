# AI MapleStory Farming Agent — Local Architecture & Class Strategies

## 1. เป้าหมาย

สร้าง AI Agent ที่ปรับแต่งมาเพื่อกลไก 2D Side-Scrolling ของ MapleStory โดยรองรับความแตกต่างของแต่ละสายอาชีพ (Class Archetypes):

- **Minimap Tracking:** มองเห็นหน้าจอเกมและอ่านพิกัดตัวเอง (จุดสีเหลือง), ผู้เล่นอื่น (จุดสีแดง), และ Portal จาก Minimap แบบ Real-time (60 FPS)
- **Class-Specific Movement:** รองรับการเคลื่อนที่เฉพาะทางของแต่ละอาชีพ (Flash Jump, Teleport, Flying, Grapple/Rope Lift)
- **Dynamic Skill & Summon Rotation:** จัดการสกิลหมู่ (AoE), สกิลวางพื้น (Summons/Installations), และสกิลที่มี Cooldown สั้น-ยาวตามรอบมอนสเตอร์เกิด (Spawn cycle ~7 วินาที)
- **Rune & Event Handling:** ตรวจจับการเกิดของ Rune บนแผนที่ เดินไปกด Spacebar และแก้ลูกศร 4 ทิศทาง (Arrow Puzzle)
- **Channel Management:** ตรวจจับความหนาแน่นของผู้เล่นในแผนที่เพื่อประเมินความคุ้มค่าในการย้ายแนล (Change Channel)
- **Strategic Optimization:** เก็บสถิติ EXP/hour, Mesos/hour, Kills/minute และให้ LLM ปรับกลยุทธ์การวาง Summon หรือเปลี่ยนเส้นทางเดินวน (Rotation) อัตโนมัติ

---

## 2. Architecture (Hybrid Fast/Slow Loop)

```text
                       ┌──────────────────────┐
                       │  MapleStory Client   │
                       └──────────┬───────────┘
                                  │ DXGI Capture (60 FPS)
              ┌───────────────────┴───────────────────┐
              │ Fast Path (16ms)                      │ Slow Path (0.5s - 5s)
              ▼                                       ▼
┌───────────────────────────┐           ┌───────────────────────────┐
│ Fast CV Layer             │           │ VLM / Specialized CV      │
│ - OpenCV (Minimap/HP/MP)  │           │ - Rune Arrow Detector     │
│ - YOLOv11n (Mobs/Orbs)    │           │ - Qwen-VL (UI/Dialogs)    │
└─────────────┬─────────────┘           └─────────────┬─────────────┘
              │                                       │
              └───────────────────┬───────────────────┘
                                  ▼
                       ┌──────────────────────┐
                       │ Structured Game State│
                       └──────────┬───────────┘
                                  │
        ┌─────────────────────────┴─────────────────────────┐
        ▼ (Every Tick: 16-30ms)                             ▼ (Every 5-15 mins / Event)
┌───────────────────────────┐                 ┌───────────────────────────┐
│ Reactive State Machine    │◄────────────────│ AI Strategic Planner      │
│ (Class Archetype Engine)  │  Update Policy  │ (Qwen3 / Local LLM)       │
│                           │                 │                           │
│ - ROTATION_FARM           │                 │ - Summon Placement Opt.   │
│ - INSTALL_SUMMONS         │                 │ - Map / Channel Selection │
│ - RUNE_SOLVING            │                 │ - Class Profile Switching │
│ - LOOT_CYCLE              │                 │ - EXP & Meso Analysis     │
│ - TOWN_RESTOCK            │                 └───────────────────────────┘
└─────────────┬─────────────┘
              │ Action Command
              ▼
┌───────────────────────────┐
│ Action Controller         │
│ - Class Movement Macro    │
│ - Keyboard/Input Driver   │
└─────────────┬─────────────┘
              │
              ▼
     MapleStory Client
```

---

## 3. Class Archetypes & Farming Strategies (การออกแบบแยกตามสายอาชีพ)

ใน MapleStory เราไม่เขียนโค้ดแยกทั้ง 40+ อาชีพ แต่จะแบ่งเป็น **4 Archetypes (กลุ่มกลไกการฟาร์ม)** เพื่อให้ State Machine โหลดโปรไฟล์ที่เหมาะสมมาใช้งาน:

### 3.1 The Teleporters (กลุ่มนักเวทย์: Bishop, Arch Mage I/L & F/P, Luminous, Battle Mage)
* **กลไกการเคลื่อนที่:** ใช้สกิล `Teleport` แทนการกระโดด Flash Jump ซึ่งสามารถวาร์ปข้ามชั้นแพลตฟอร์ม (แกน Y) ได้ทันทีหากระยะความสูงไม่เกินระยะสกิล
* **กลยุทธ์การฟาร์ม (Teleport Casting):**
  * กด `สกิลโจมตี + Teleport + ปุ่มทิศทาง` พร้อมกัน (Animation Canceling)
  * **Bishop / F/P:** เน้นวางสกิลครอบคลุมพื้นที่ (เช่น *Fountain of Vengeance*, *Erda Shower*) ไว้ฝั่งหนึ่งของแมพ แล้วใช้ Teleport วนเคลียร์อีกฝั่ง
  * **Luminous:** ต้องให้ Vision อ่านสถานะ **Equilibrium (Light/Dark State)** บนหน้าจอ เพื่อสลับใช้สกิล *Reflection* (ชิ่งมอนสเตอร์ระยะไกล) และสกิลมืดตามสถานะบัฟ

### 3.2 The Projectile & Mark Assassins (กลุ่มดาวกระจาย/ลูกธนูชิ่ง: Night Lord, Night Walker, Wind Archer, Mechanic)
* **กลไกการเคลื่อนที่:** ความคล่องตัวสูงมาก มีทั้ง Flash Jump 2 จังหวะ, พุ่งตัวแนวเฉียง (Shadow Leap / Dash)
* **กลยุทธ์การฟาร์ม (Centralized & Mark Farming):**
  * อาชีพกลุ่มนี้เมื่อโจมตีจะมีวัตถุวิถีโค้ง (Assassin's Mark / Shadow Bat) บินไปฆ่ามอนสเตอร์ทั้งจอเองหากดาเมจถึง (One-shot Mark)
  * **กลยุทธ์ AI:** ไม่จำเป็นต้องเดินให้ทั่วทุกมุมแมพ ให้เน้นกระโดดอยู่ **โซนกึ่งกลางแผนที่ (Center Platform)** แล้ววาง *Dark Flare* + *Erda Fountain* ดักไว้ที่มุมซ้ายและขวาสุด

### 3.3 The Micro-Summon / Area Controllers (กลุ่มคุมพื้นที่: Lara, Corsair, Kanna, Illium)
* **กลไกการเคลื่อนที่:** เคลื่อนที่ปานกลาง แต่เน้นการยืนตำแหน่งที่แม่นยำเพื่อวางยูนิตซัมมอน
* **กลยุทธ์การฟาร์ม (Cycle & Refresh Strategy):**
  * **Lara (Dragon Vein Reading):** ต้องเพิ่มโมเดล YOLO สำหรับตรวจจับ **Dragon Vein (จุดชีพจรธาตุสีต่างๆ บนพื้น)** AI ต้องเดินไปเหยียบจุดเหล่านั้นแล้วกดสกิล *Eruption* (น้ำ/ลม/ไฟ) ให้ครอบคลุมทั้งแมพ จากนั้นยืนนิ่งๆ รอเก็บของและวนไปกดรีเฟรชสกิลทุกๆ 15-18 วินาที
  * **Corsair:** เน้นวางลูกเรือ (*Broadside*, *Siege Bomber*) ทั้งสองฝั่งของแมพ แล้วกดรีเฟรชทุก 30-60 วินาที

### 3.4 The Active Sweepers & Gauge Managers (กลุ่มนักรบ/กวาดจอ: Adele, Dawn Warrior, Buccaneer, Khali)
* **กลไกการเคลื่อนที่:** กว้างและรวดเร็วมาก (Buccaneer ใช้ *Super Jump* พุ่งข้ามแมพได้ในพริบตา)
* **กลยุทธ์การฟาร์ม (Full Rotation & Passive Aura):**
  * **Buccaneer (Lord of the Deep):** เปิดสกิลมังกรหมุนรอบตัว แล้วใช้เทคนิคกระโดดพุ่งชนมอนสเตอร์ไปรอบแมพโดยแทบไม่ต้องกดปุ่มโจมตีหลัก (ต้องคอยอ่านค่า **Energy Gauge** ไม่ให้หมด)
  * **Adele:** ต้องคอยกดซัมมอนดาบ (*Order*) ให้บินไปฟันมอนสเตอร์อัตโนมัติ โดยต้องอ่าน **Aether Gauge** จาก UI เสมอ
  * **Dawn Warrior:** สกิลหลักมีรัศมีกว้างเกือบครึ่งจอ เน้นยืนบนแพลตฟอร์มระดับกลางเพื่อตีรวบทั้งชั้นบนและชั้นล่างพร้อมกัน

---

## 4. ตารางเปรียบเทียบพารามิเตอร์ของแต่ละสายอาชีพ

| อาชีพ / กลุ่ม | รูปแบบการเคลื่อนที่หลัก | รัศมีสกิล (AoE) | การพึ่งพา Summon | ค่าพิเศษที่ Vision ต้องอ่านเพิ่ม |
|---|---|---|---|---|
| **Bishop / Mage** | Teleport (X และ Y) | ปานกลาง | สูง (Fountain/Door) | Cooldown ของ Infinity / Bahamut |
| **Night Lord / NW** | Flash Jump + Dash | กว้าง (Mark ชิ่งทั้งจอ) | ปานกลาง (Dark Flare) | จำนวนดาวกระจาย / สถานะ Mark |
| **Lara** | Flash Jump | กว้างมาก (วางพื้น) | สูงที่สุด (3 Eruptions) | ตำแหน่งและสีของ Dragon Vein บนพื้น |
| **Buccaneer** | Super Jump (พุ่งเร็ว) | แคบ (ติดตัวละคร) | ต่ำ | หลอด Energy Gauge และสถานะมังกร |
| **Adele** | Flash Jump + Impale | กว้าง | ปานกลาง (Blossom/Territory) | จำนวนดาบที่ลอยอยู่ และหลอด Aether |

---

## 5. AI Strategic Planner (กลยุทธ์การตัดสินใจด้วย LLM)

ใน Slow Loop (ทำงานทุก 5-15 นาที) **Qwen3** จะรับข้อมูลสถิติจากฐานข้อมูลมาวิเคราะห์และปรับพารามิเตอร์ของ State Machine ดังนี้:

### 5.1 กลยุทธ์การเลือกแผนที่ตามความสามารถในการทำดาเมจ (One-Shot Check)
* **กฎเหล็กของ MapleStory:** การฟาร์มจะมีประสิทธิภาพสูงสุดเมื่อสกิลหลักฆ่ามอนสเตอร์ตายในครั้งเดียว (One-shot)
* **LLM Logic:**
  1. ตรวจสอบค่า `Kills/min` เทียบกับ `Max Spawn Limit` ของแผนที่นั้นๆ
  2. หากพบว่าตัวละครต้องกดสกิลซ้ำ 2-3 ครั้งมอนสเตอร์ถึงจะตาย (Two/Three-shotting) ส่งผลให้ `Kills/min` ต่ำกว่าเกณฑ์
  3. **Action:** LLM จะสั่งเปิดบัฟเพิ่มดาเมจ (เช่น กด Guild Buff, ยาเพิ่มพลังโจมตี) หรือสั่งเปลี่ยนเป้าหมายไปยังแผนที่ที่มอนสเตอร์เลเวลต่ำลงแต่ฆ่าตายในทีเดียว ซึ่งมักจะได้ `EXP/hour` สุทธิสูงกว่า

### 5.2 กลยุทธ์การจัดวาง Summon อัตโนมัติ (Dynamic Summon Optimization)
* ทุกอาชีพในเลเวล 260+ จะมีสกิลกลางคือ **Sol Janus (Dusk / Dawn)** และ **Erda Shower (Erda Fountain)**
* **LLM Logic:**
  1. สร้าง Heatmap จากตำแหน่งที่ YOLO ตรวจพบมอนสเตอร์ตกค้าง (มอนสเตอร์ที่ไม่ตายในรอบการเดินปกติ)
  2. คำนวณหาจุดกึ่งกลางของกลุ่มมอนสเตอร์ที่ตกค้างบ่อยที่สุด
  3. **Action:** อัปเดตพิกัด `summon_waypoint: [x, y]` ในไฟล์ Config ของ State Machine เพื่อให้รอบถัดไปตัวละครเดินไปวาง *Erda Fountain* หรือ *Sol Janus* ณ จุดนั้นแทน

### 5.3 กลยุทธ์การบริหารรอบเก็บของ (Loot Cycle Strategy)
* ในเวลาปกติ สัตว์เลี้ยง (Pet) จะเก็บของตามทางที่ตัวละครกระโดดผ่าน แต่พื้นที่ที่วาง Summon ทิ้งไว้จะมีถุงเงิน (Meso Bags) กองอยู่เป็นจำนวนมาก
* **LLM Logic:**
  * แบ่งลูปการทำงานออกเป็น **15 รอบ (ประมาณ 105 วินาที)**
  * **รอบที่ 1 - 13 (Kill Focus):** กระโดดโจมตีด้วยความเร็วสูงสุดในโซนหลัก ไม่แวะไปจุดที่วาง Summon
  * **รอบที่ 14 - 15 (Loot & Refresh Cycle):** เดินอ้อมไปยังจุดที่วาง *Erda Fountain* และ *Sol Janus* เพื่อเก็บถุงเงินทั้งหมดก่อนที่ของจะจางหายไป (Despawn ที่ ~120 วินาที) พร้อมกับกดวาง Summon ใหม่ในจังหวะเดียวกัน

### 5.4 กลยุทธ์การคำนวณตัวคูณ EXP และการกด Rune (Multiplier Synchronization)
* **LLM Logic:**
  * ตรวจสอบเวลาคงเหลือของคูปองคูณประสบการณ์ (2x/3x EXP Coupon, MVP Buff, Gold Potion)
  * เมื่อตรวจพบว่ามี **Rune** เกิดขึ้นในแผนที่ LLM จะประเมินว่าควรรีบไปกดทันที หรือรอให้สกิลกวาดล้างจอใหญ่ (Full Map Attack / Burst Skill Cooldown 60-180s) พร้อมใช้งานก่อนค่อยไปกด Rune เพื่อรีดประสิทธิภาพจากบัฟ **Rune +100% EXP** ให้ได้สูงสุดในช่วงที่มีสกิลใหญ่

---

## 6. ตัวอย่าง Class Configuration Schema (`configs/classes/`)

State Machine จะอ่านไฟล์ YAML ของแต่ละอาชีพเพื่อปรับเปลี่ยนพฤติกรรมโดยไม่ต้องแก้โค้ดหลัก:

```yaml
# ตัวอย่างไฟล์: configs/classes/bishop.yaml
class_name: "Bishop"
archetype: "TELEPORTER"

movement:
  type: "teleport"
  teleport_key: "shift"
  horizontal_distance_px: 22      # ระยะวาร์ปแนวราบเทียบบน Minimap
  vertical_reach_px: 18           # ระยะวาร์ปข้ามชั้นแนวตั้งบน Minimap
  rope_lift_key: "v"

skills:
  main_mobbing:
    name: "Big Bang"
    key: "ctrl"
    cast_with_teleport: true      # กดพร้อม Teleport ได้

  summons:
    - name: "Fountain of Vengeance"
      key: "a"
      cooldown_sec: 58.0
      preferred_zone: "left_platforms"
    - name: "Erda Fountain"
      key: "s"
      cooldown_sec: 58.0
      preferred_zone: "right_platforms"
    - name: "Bahamut"
      key: "d"
      cooldown_sec: 260.0
      preferred_zone: "any"

  map_clears:
    - name: "Peacemaker"
      key: "f"
      cooldown_sec: 10.0
    - name: "Genesis"
      key: "g"
      cooldown_sec: 30.0

  buffs:
    - name: "Decent Holy Symbol"
      key: "1"
      cooldown_sec: 180.0
    - name: "Infinity"
      key: "2"
      cooldown_sec: 180.0

strategy:
  loot_cycle_interval_sec: 95
  prioritize_rune_with_fmas: true # เก็บสกิลใหญ่ไว้กดตอนได้บัฟ Rune
```

---

## 7. โครงสร้าง Game State ที่รองรับหลายอาชีพ

เพิ่มฟิลด์ `class_specific` ใน JSON เพื่อให้รองรับเกจและสถานะพิเศษของแต่ละอาชีพ:

```json
{
  "map_name": "Carcion: Calm Beach 3",
  "channel": 8,
  "minimap": {
    "player_pos": [78, 95],
    "other_players_count": 0,
    "rune_pos": null,
    "summon_positions": {
      "erda_fountain": [30, 95],
      "sol_janus_1": [125, 60]
    }
  },
  "status": {
    "hp_ratio": 1.0,
    "mp_ratio": 0.85,
    "exp_percent": 72.104,
    "rune_buff_active": true,
    "exp_coupon_remaining_sec": 840
  },
  "class_specific": {
    "archetype": "SUMMONER_LARA",
    "gauge_ratio": 0.90,
    "detected_veins": [
      {"type": "river", "screen_x": 400, "screen_y": 550},
      {"type": "wind", "screen_x": 950, "screen_y": 320}
    ],
    "active_eruptions": ["river", "sun"]
  },
  "metrics_current_session": {
    "kills_per_minute": 288,
    "max_map_spawn_per_min": 296,
    "map_clear_efficiency": 0.972
  }
}
```

---

## 8. Recommended Project Structure (Updated for Multi-Class)

```text
maplestory-ai-agent/
├── app/
│   ├── capture/
│   │   └── dxgi_capture.py         # ดึงภาพหน้าจอความเร็วสูง (60 FPS)
│   │
│   ├── vision/
│   │   ├── minimap_tracker.py      # OpenCV อ่านพิกัดผู้เล่น, คนอื่น, และ Rune
│   │   ├── status_ocr.py           # อ่านหลอด HP/MP, EXP%, และจำนวน Mesos
│   │   ├── class_gauge_reader.py   # อ่านเกจเฉพาะอาชีพ (Luminous/Buccaneer/Adele/Lara Veins)
│   │   ├── mob_detector.py         # YOLOv11 ตรวจจับกลุ่มมอนสเตอร์และ Elite Boss
│   │   ├── rune_solver.py          # โมเดลแยกแยะทิศทางลูกศร Rune ทั้ง 4 ลูก
│   │   └── vlm_inspector.py        # Qwen-VL สำหรับตรวจจับหน้าต่างแจ้งเตือนและแชท
│   │
│   ├── navigation/
│   │   ├── platform_graph.py       # โครงสร้างข้อมูลแพลตฟอร์มและเชือกของแต่ละแมพ
│   │   ├── pathfinder.py           # คำนวณเส้นทาง A* (ปรับตาม Flash Jump หรือ Teleport)
│   │   └── movement_macros.py      # ท่ากระโดด/วาร์ปเฉพาะของแต่ละ Archetype
│   │
│   ├── state_machine/
│   │   ├── core_fsm.py             # ตัวจัดการเปลี่ยนสถานะหลัก
│   │   ├── archetypes/             # ลอจิกการฟาร์มแยกตามกลุ่มอาชีพ
│   │   │   ├── teleporter_fsm.py
│   │   │   ├── projectile_fsm.py
│   │   │   ├── summoner_fsm.py
│   │   │   └── sweeper_fsm.py
│   │   ├── rune_state.py           # ลำดับขั้นตอนการเดินไปหาและแก้ Rune
│   │   └── loot_cycle.py           # ลูปการเดินเก็บถุงเงินตามจุดวาง Summon
│   │
│   ├── agent/
│   │   ├── strategic_planner.py    # Qwen3 วิเคราะห์ Efficiency และปรับจุดวาง Summon
│   │   ├── buff_synchronizer.py    # บริหารเวลาคูปอง EXP และบัฟใหญ่อัตโนมัติ
│   │   └── memory_db.py            # บันทึกสถิติลงฐานข้อมูล
│   │
│   ├── controller/
│   │   ├── timing_jitter.py        # สร้าง Gaussian noise ให้จังหวะการกดปุ่ม
│   │   └── input_driver.py         # โมดูลส่งคำสั่งควบคุมคีย์บอร์ด
│   │
│   └── main.py
│
├── configs/
│   ├── maps/                       # พิกัดแพลตฟอร์มของแต่ละแมพ
│   │   ├── limina_1_4.yaml
│   │   └── carcion_beach_3.yaml
│   └── classes/                    # โปรไฟล์สกิลของแต่ละอาชีพ
│       ├── bishop.yaml
│       ├── night_lord.yaml
│       ├── lara.yaml
│       └── buccaneer.yaml
├── models/
├── logs/
└── README.md
```