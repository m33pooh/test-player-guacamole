# AI MapleStory Farming Agent — Local Architecture

## 1. เป้าหมาย

สร้าง AI Agent ที่ปรับแต่งมาเพื่อกลไก 2D Side-Scrolling ของ MapleStory โดยเฉพาะ:

- **Minimap Tracking:** มองเห็นหน้าจอเกมและอ่านพิกัดตัวเอง (จุดสีเหลือง), ผู้เล่นอื่น (จุดสีแดง), และ Portal จาก Minimap แบบ Real-time (60 FPS)
- **2D Platform Navigation:** เคลื่อนที่ตามแกน X-Y (กระโดดขึ้นชั้นบน, ลงชั้นล่าง, ปีนเชือก, ใช้ Rope Lift, Flash Jump, Teleport)
- **Mobbing & Skill Rotation:** ใช้สกิลหมู่ (AoE) กวาดมอนสเตอร์ตามรอบเกิด (Spawn cycle ~7 วินาที) กดสกิลซัมมอน (Erda Shower/Fountain) และกด Buff ตามเวลา
- **Rune & Anti-Bot Solver:** ตรวจจับการเกิดของ Rune บนแผนที่ เดินไปกด Spacebar และแก้ลูกศร 4 ทิศทาง (Arrow Puzzle)
- **Anti-KS & Channel Surfing:** ตรวจจับผู้เล่นอื่นในแผนที่ หากมีคนมาแย่งฟาร์ม (KS) หรือแผนที่ไม่ว่าง ให้เปลี่ยนแนล (Change Channel) อัตโนมัติ
- **Performance & Analytics:** เก็บสถิติ EXP/hour, Mesos/hour, Kills/hour และปรับกลยุทธ์การเดินวน (Rotation) จากข้อมูลที่สะสม

> **หมายเหตุ:** สำหรับเกมออนไลน์จริง การทำ bot/automation ขัดกับ Terms of Service และระบบ Anti-Cheat ของเกม เอกสารฉบับนี้ออกแบบมาเพื่อการศึกษาโครงสร้างทางเทคนิคด้าน Computer Vision และ AI State Machine เท่านั้น

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
│ - YOLOv11n (Mobs/Runes)   │           │ - Qwen-VL (UI/Dialogs/GM) │
└─────────────┬─────────────┘           └─────────────┬─────────────┘
              │                                       │
              └───────────────────┬───────────────────┘
                                  ▼
                       ┌──────────────────────┐
                       │ Structured Game State│
                       └──────────┬───────────┘
                                  │
        ┌─────────────────────────┴─────────────────────────┐
        ▼ (Every Tick)                                      ▼ (Event / Timer Trigger)
┌───────────────────────────┐                 ┌───────────────────────────┐
│ Reactive State Machine    │◄────────────────│ AI Strategic Planner      │
│                           │  Update Policy  │ (Qwen3 / Local LLM)       │
│ - ROTATION_FARM           │                 │                           │
│ - RUNE_SOLVING            │                 │ - Route Optimization      │
│ - BUFF_AND_SUMMON         │                 │ - Map / Channel Selection │
│ - ELITE_COMBAT            │                 │ - Chat / GM Response      │
│ - CHANGE_CHANNEL          │                 │ - EXP & Meso Analysis     │
│ - TOWN_RESTOCK            │                 └───────────────────────────┘
└─────────────┬─────────────┘
              │ Action Command
              ▼
┌───────────────────────────┐
│ Action Controller         │
│ - Gaussian Timing Jitter  │
│ - Keyboard/Input Driver   │
└─────────────┬─────────────┘
              │
              ▼
     MapleStory Client
```

---

## 3. หลักการสำคัญ (3-Tier Hierarchy)

ไม่ควรให้ VLM/LLM ควบคุมการกดปุ่มทุกเฟรม เพราะความหน่วง (Latency 200-500ms) จะทำให้ตัวละครกระโดดเลยแพลตฟอร์ม ต้องแบ่งการทำงานเป็น 3 ระดับ:

```text
Screenshot (60 FPS)
    ↓
Fast CV (OpenCV + YOLO) & Event VLM (Qwen-VL)
    ↓
Structured Game State (JSON)
    ↓
Reactive State Machine (Fast Loop: 16-30ms)
    ↓
LLM Strategic Planner (Slow Loop: 5-15 mins / Event-driven)
    ↓
Action Controller
```

### 3.1 Vision Layer
- **OpenCV (Latency < 5ms):**
  - **Minimap Tracker:** Crop เฉพาะกรอบ Minimap มุมซ้ายบน ใช้ Color Masking หาพิกัด `(x, y)` ของจุดสีเหลือง (ผู้เล่น), จุดสีแดง (ผู้เล่นอื่น), และจุดสีม่วง (Rune)
  - **HP/MP/EXP Reader:** อ่านสัดส่วน Pixel สีจากหลอดเลือด/มานา และใช้ OCR ขนาดเล็กอ่านตัวเลข EXP/Mesos
- **YOLOv11-Nano (Latency 5-10ms):**
  - ตรวจจับ Bounding Box ของกลุ่มมอนสเตอร์, ตำแหน่งเสา Rune บนหน้าจอจริง, ลูกแก้ว Combo Orb, และ Elite Boss
- **Rune Classifier & Qwen-VL (เรียกใช้ตาม Event):**
  - **Rune Solver Model:** โมเดล CNN/YOLO เฉพาะทางสำหรับอ่านลูกศร 4 ทิศทางตอนกดแก้อักษรรูน
  - **Qwen2.5-VL:** เรียกใช้เมื่อเกิดสถานะผิดปกติ เช่น ถูกดึงเข้าห้องตรวจสอบ, มีหน้าต่าง Dialog เด้งขึ้นมา, หรือมีคนพิมพ์แชททักทาย

### 3.2 Reactive State Machine
รับผิดชอบ Action ที่ต้องการความเร็วสูงและแม่นยำตามรอบการเกิดของมอนสเตอร์:

```text
ROTATION_FARM (เดินและกระโดดโจมตีตาม Waypoints บน Minimap)
 ├─ rune_active == true & rune_cooldown == false ──► RUNE_SOLVING
 ├─ buff_expired == true or summon_expired == true ─► BUFF_AND_SUMMON
 ├─ other_player_duration > 10s ───────────────────► CHANGE_CHANNEL
 ├─ elite_boss_spawned == true ────────────────────► ELITE_COMBAT
 ├─ hp < 0.30 ─────────────────────────────────────► EMERGENCY_HEAL
 ├─ inventory_full == true or potion_low == true ──► TOWN_RESTOCK
 └─ anomaly_detected ──────────────────────────────► ALERT_RECOVERY
```

### 3.3 LLM Strategic Planner
รับผิดชอบการตัดสินใจเชิงกลยุทธ์ (ทำงานเบื้องหลัง):
- วิเคราะห์ความคุ้มค่าของแผนที่จาก `Kills/min` และ `EXP/hour`
- ปรับตำแหน่งการวางสกิล Summon (เช่น Erda Fountain) ให้ครอบคลุมจุดที่มอนสเตอร์เกิดหนาแน่นแต่ไปถึงช้า
- วิเคราะห์และสร้างข้อความตอบกลับเมื่อมีผู้เล่นอื่นพิมพ์คุยด้วยในช่องแชท

---

## 4. Game State

Vision Layer แปลงภาพหน้าจอเป็น Structured State ก่อนส่งให้ State Machine และ LLM:

```json
{
  "map_name": "Limina: End of the World 1-4",
  "channel": 14,
  "minimap": {
    "player_pos": [64, 112],
    "other_players_count": 0,
    "rune_pos": [42, 85],
    "portals": [[12, 112], [140, 112]]
  },
  "status": {
    "hp_ratio": 0.95,
    "mp_ratio": 0.78,
    "exp_percent": 45.621,
    "rune_buff_active": false,
    "rune_debuff_cooldown": false,
    "dead": false
  },
  "combat": {
    "mob_clusters": [
      {"center_x": 450, "center_y": 600, "count": 8},
      {"center_x": 1200, "center_y": 350, "count": 6}
    ],
    "elite_monster_present": false,
    "off_cooldown_skills": ["erda_fountain", "decent_holy_symbol", "burst_skill"]
  },
  "security": {
    "dialog_open": false,
    "unexpected_map_change": false,
    "chat_activity": false
  }
}
```

---

## 5. Combat & Rotation State Machine

การต่อสู้ใน MapleStory คือการเดินวนตามแพลตฟอร์ม (Map Rotation) เป็นลูปต่อเนื่อง:

```text
              ┌────────────────────┐
              │   ROTATION_FARM    │
              └─────────┬──────────┘
                        │
          เดินตาม Waypoint (X, Y) บน Minimap
                        │
                        ▼
              ┌────────────────────┐
              │  PLATFORM_MOVEMENT │ (Flash Jump / Teleport / Rope Lift)
              └─────────┬──────────┘
                        │
                อยู่ในระยะโจมตี
                        │
                        ▼
              ┌────────────────────┐
              │    AOE_ATTACK      │ (ใช้สกิลกวาดมอนสเตอร์)
              └─────────┬──────────┘
                        │
             เช็คเงื่อนไขพิเศษก่อนไปจุดถัดไป
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
  [เช็ค Cooldown]   [เช็คจุดสีม่วง]    [เช็คจุดสีแดง]
        │               │               │
        ▼               ▼               ▼
  วาง Erda Fountain  เดินไปแก้ Rune    เปลี่ยนแนล (CC)
```

---

## 6. Rune Solving & Farming Loop

```text
START FARMING
  ↓
อ่านพิกัดตัวเองบน Minimap (x, y)
  ↓
เช็คสถานะความปลอดภัย (HP/MP, คนอื่นในแมพ, ห้องตรวจสอบ)
  ↓
ตรวจสอบว่ามี Rune เกิดหรือไม่ (จุดสีม่วงบน Minimap)
  ├── มี (และไม่ติด Cooldown) ──► เดินไปที่พิกัด (rune_x, rune_y)
  │                                  ↓
  │                             กด Spacebar
  │                                  ↓
  │                             อ่านลูกศร 4 ทิศทางด้วย CNN/YOLO
  │                                  ↓
  │                             กดปุ่มลูกศรตามลำดับ → กลับไปฟาร์มต่อ
  │
  └── ไม่มี ──► เดิน/กระโดดไปยัง Waypoint ถัดไปในลูป Rotation
                    ↓
              กดสกิลโจมตีหลัก (Mobbing Skill)
                    ↓
              เช็คเวลา Summon / Buff (กดซ้ำเมื่อหมดเวลา)
                    ↓
              เช็คกระเป๋า / ยาปั๊ม
                    ├── ยังว่าง ──► วนลูป Waypoint ถัดไป
                    └── เต็ม ────► กลับเมือง → ขาย/เก็บของ → กลับมาฟาร์ม
```

---

## 7. 2D Platform Navigation (ระบบนำทาง)

สร้าง **Platform Graph** ของแต่ละแผนที่เพื่อคำนวณการกระโดดข้ามชั้น:

```text
[Platform ชั้นบน: Y=80, X=20..120]
         ▲                  │
         │ (Rope Lift)      │ (Down + Jump)
         │                  ▼
[Platform ชั้นล่าง: Y=112, X=10..150]
```

- **การเดินแนวราบ (X-axis):** หากระยะห่างมากกว่า 30 พิกเซลบน Minimap ให้กด `Jump + Jump + Attack` (Flash Jump Attack) หากใกล้เป้าหมายให้เดินปกติเพื่อความแม่นยำ (เช่น ตอนจะยืนกด Rune)
- **การขึ้นชั้นบน (Upward Y-axis):** ใช้สกิล `Rope Lift` หรือ `Up + Jump`
- **การลงชั้นล่าง (Downward Y-axis):** กด `Down + Jump` พร้อมกัน

---

## 8. Memory & Performance Logging

### 8.1 Map & Rotation Memory
เก็บสถิติของแต่ละแผนที่และรูปแบบการเดินแยกตามคลาสตัวละคร:

```json
{
  "map_name": "Limina: End of the World 1-4",
  "character_class": "Night Lord",
  "rotation_profile": "clockwise_fountain_left",
  "kills_per_minute": 265,
  "exp_per_hour": "185B",
  "mesos_per_hour": "420M",
  "rune_success_rate": 0.98
}
```

### 8.2 Action & Event Logging
บันทึกข้อมูลลง SQLite / PostgreSQL เพื่อนำไปวิเคราะห์:

```text
timestamp
state
action
minimap_x
minimap_y
exp_delta
meso_delta
hp_ratio
mp_ratio
channel
```

จากนั้นคำนวณบน Dashboard:
- `EXP/hour` & `Mesos/hour`
- `Kills/minute` (เทียบกับเพดานสูงสุดของแผนที่)
- `Rune Solve Time` (เวลาเฉลี่ยที่ใช้ในการเดินไปกดและแก้รูน)
- `Channel Surf Frequency` (ความถี่ในการต้องย้ายแนลหนีคนอื่น)

---

## 9. Learning Pipeline

เริ่มต้นจากระบบ Hybrid (Rule-based + Vision) แล้วค่อยพัฒนาสู่ Machine Learning เต็มรูปแบบ:

1. **Phase 1 — Waypoint & State Machine:** กำหนดจุดเดินและจุดวาง Summon บน Minimap ด้วยไฟล์ Config
2. **Phase 2 — Imitation Learning (Behavior Cloning):** บันทึกการเล่นของมนุษย์ในแผนที่นั้นๆ (ภาพ Minimap + ปุ่มที่กด ณ พิกัดต่างๆ) เพื่อให้โมเดลเรียนรู้จังหวะการกระโดด Flash Jump ที่ลื่นไหลแบบมนุษย์
3. **Phase 3 — Reinforcement Learning (Route Optimization):** ให้ AI ทดลองขยับจุดวาง Summon และลำดับการกระโดด โดยมี Reward คือจำนวน `Kills per minute` ที่สูงขึ้น

---

## 10. Hardware Allocation (RTX 5090 — 32GB VRAM)

สามารถรันทุกส่วนพร้อมกันในเครื่องเดียวโดยไม่ทำให้ตัวเกมกระตุก:

```text
RTX 5090 (32GB VRAM)
 ├── MapleStory Client (1366x768)        : ~2.0 GB
 ├── YOLOv11s + Rune Arrow CNN           : ~1.5 GB (ทำงานระดับมิลลิวินาที)
 ├── Qwen2.5-VL-7B (FP8/AWQ)             : ~6.5 GB (ตรวจจับ UI / ห้องตรวจสอบ / แชท)
 ├── Qwen3-14B (Q4_K_M / AWQ)            : ~10.0 GB (วางแผนกลยุทธ์ / ตอบแชท)
 └── System, OpenCV & Buffer             : ~3.0 GB
 ----------------------------------------------------
 รวมการใช้งาน VRAM ประมาณ ~23.0 GB (เหลือสำรอง ~9.0 GB)
```

---

## 11. Suggested Software Stack

| Component | Technology |
|---|---|
| **Fast Vision (Minimap/UI)** | OpenCV + RapidOCR / EasyOCR |
| **Object & Rune Detection** | YOLOv11 (Ultralytics) + Custom CNN Classifier |
| **Event VLM** | Qwen2.5-VL (รันผ่าน vLLM / Ollama) |
| **Strategic LLM** | Qwen3-14B |
| **Screen Capture** | `dxcam` (DXGI Desktop Duplication API 60+ FPS) |
| **Agent Core & State** | Python 3.11+ / Pydantic |
| **Database** | SQLite (Prototype) → PostgreSQL |
| **API & Dashboard** | FastAPI + React (แสดงกราฟ EXP/Meso และสถานะบอท) |
| **GPU Runtime** | PyTorch / CUDA / TensorRT |

---

## 12. Recommended Project Structure

```text
maplestory-ai-agent/
├── app/
│   ├── capture/
│   │   └── dxgi_capture.py         # ดึงภาพหน้าจอความเร็วสูง (60 FPS)
│   │
│   ├── vision/
│   │   ├── minimap_tracker.py      # OpenCV อ่านพิกัดผู้เล่น, คนอื่น, และ Rune
│   │   ├── status_ocr.py           # อ่านหลอด HP/MP, EXP%, และจำนวน Mesos
│   │   ├── mob_detector.py         # YOLOv11 ตรวจจับกลุ่มมอนสเตอร์และ Elite Boss
│   │   ├── rune_solver.py          # โมเดลแยกแยะทิศทางลูกศร Rune ทั้ง 4 ลูก
│   │   └── vlm_inspector.py        # Qwen-VL สำหรับตรวจจับหน้าต่างแจ้งเตือนและแชท
│   │
│   ├── navigation/
│   │   ├── platform_graph.py       # โครงสร้างข้อมูลแพลตฟอร์มและเชือกของแต่ละแมพ
│   │   └── pathfinder.py           # คำนวณเส้นทาง A* บนแพลตฟอร์ม 2 มิติ
│   │
│   ├── state_machine/
│   │   ├── core_fsm.py             # ตัวจัดการเปลี่ยนสถานะหลัก
│   │   ├── rotation_farm.py        # ลูปการเดินวนตีมอนสเตอร์และวาง Summon
│   │   ├── rune_state.py           # ลำดับขั้นตอนการเดินไปหาและแก้ Rune
│   │   └── channel_surfer.py       # ระบบเปลี่ยนแนลและจัดการเหตุฉุกเฉิน
│   │
│   ├── agent/
│   │   ├── strategic_planner.py    # Qwen3 วิเคราะห์อัตรา EXP/Meso และปรับแผนการฟาร์ม
│   │   ├── social_responder.py     # วิเคราะห์และจัดการข้อความแชท
│   │   └── memory_db.py            # บันทึกสถิติลงฐานข้อมูล
│   │
│   ├── controller/
│   │   ├── timing_jitter.py        # สร้าง Gaussian noise ให้จังหวะการกดปุ่มเป็นธรรมชาติ
│   │   └── input_driver.py         # โมดูลส่งคำสั่งควบคุมคีย์บอร์ดและเมาส์
│   │
│   └── main.py
│
├── configs/
│   ├── maps/                       # ตั้งค่าพิกัดแพลตฟอร์มและจุดวาง Summon ของแต่ละแมพ
│   │   └── limina_1_4.yaml
│   └── classes/                    # ตั้งค่าปุ่มสกิลและ Cooldown ของแต่ละอาชีพ
│       └── night_lord.yaml
├── models/                         # เก็บไฟล์ Weight ของ YOLO และ Rune Classifier
├── data/                           # เก็บ Dataset สำหรับเทรนลูกศร Rune และ Imitation Learning
├── logs/
└── README.md
```

---

## 13. Development Milestones

### M1 — Minimap & Status Vision
- [ ] ดึงภาพหน้าจอเกมที่ 60 FPS ด้วย `dxcam`
- [ ] ใช้ OpenCV ระบุพิกัด `(x, y)` ของจุดสีเหลือง (ผู้เล่น) บน Minimap
- [ ] ตรวจจับจุดสีม่วง (Rune) และจุดสีแดง (ผู้เล่นอื่น) บน Minimap
- [ ] อ่านค่าสัดส่วน HP/MP และตัวเลข EXP

### M2 — 2D Platform Movement
- [ ] สร้างระบบส่งคำสั่งกดปุ่มพร้อมตัวสุ่มเวลาหน่วง (Gaussian Timing Jitter)
- [ ] เดินซ้าย-ขวาไปยังพิกัด `X` ที่กำหนดบน Minimap
- [ ] กระโดดขึ้นชั้นบน (`Rope Lift` / `Up+Jump`) และลงชั้นล่าง (`Down+Jump`) ไปยังพิกัด `Y`
- [ ] ตรวจจับอาการเดินติดขอบหรือตกแพลตฟอร์ม พร้อมระบบเดินกลับเข้าลูป

### M3 — Rotation & Skill Manager
- [ ] สร้างไฟล์ Config กำหนดลำดับ Waypoint การเดินวนในแผนที่
- [ ] ผสานการกระโดด Flash Jump เข้ากับการกดสกิลโจมตีหลัก
- [ ] สร้างตัวจับเวลา (Cooldown Tracker) สำหรับกดสกิล Buff และวาง Summon ประจำจุด

### M4 — Rune Solver & Channel Surfing
- [ ] เทรนโมเดลตรวจจับลูกศร 4 ทิศทางของ Rune
- [ ] สร้าง State เดินไปหาเสา Rune กด Spacebar และส่งคำสั่งกดลูกศรตามที่โมเดลอ่านได้
- [ ] สร้างระบบเปลี่ยนแนลอัตโนมัติเมื่อตรวจพบผู้เล่นอื่นอยู่ในแผนที่เกินเวลาที่กำหนด

### M5 — VLM/LLM Integration & Analytics
- [ ] เชื่อมต่อ Qwen-VL เพื่อตรวจสอบหน้าต่างแจ้งเตือนผิดปกติและอ่านข้อความในช่องแชท
- [ ] สร้าง Dashboard คำนวณ `EXP/hour`, `Mesos/hour`, และ `Kills/minute`
- [ ] เชื่อมต่อ Qwen3 เพื่อวิเคราะห์ข้อมูลสถิติและปรับปรุงเส้นทาง Rotation