# AI MMORPG Farming Agent — Local Architecture

## 1. เป้าหมาย

สร้าง AI Agent ที่สามารถ:

- มองเห็นหน้าจอเกม
- ตรวจจับตัวละคร ศัตรู HP/MP และสถานะสำคัญ
- ตัดสินใจว่าจะทำอะไรต่อ
- ควบคุม keyboard/mouse
- ต่อ combat → loot → inventory → กลับเมือง → ขาย/เก็บของ → กลับไปฟาร์ม
- เก็บสถิติ XP/hour, Gold/hour, death rate
- ปรับกลยุทธ์การฟาร์มจากข้อมูลที่สะสม

> หมายเหตุ: สำหรับ MMORPG จริง เช่น Ragnarok, WoW, FFXIV และ Black Desert การทำ bot/automation อาจขัดกับ Terms of Service หรือระบบ anti-cheat ของเกม ควรทดลองกับเกม/เซิร์ฟเวอร์ที่อนุญาตให้ automation ก่อน

---

## 2. Architecture

```text
                    ┌──────────────────┐
                    │      Game        │
                    └────────┬─────────┘
                             │ Screenshot
                             ▼
                    ┌──────────────────┐
                    │ Vision Model     │
                    │ Qwen-VL / VLM    │
                    └────────┬─────────┘
                             │
                     Game State
                             ▼
                    ┌──────────────────┐
                    │ State Machine    │
                    │                  │
                    │ FARM             │
                    │ COMBAT           │
                    │ LOOT             │
                    │ HEAL             │
                    │ TOWN             │
                    │ RECOVER          │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ AI Planner       │
                    │ Qwen3 / LLM     │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Action Controller│
                    │ Keyboard/Mouse   │
                    └────────┬─────────┘
                             │
                             ▼
                           Game
```

---

## 3. หลักการสำคัญ

ไม่ควรให้ LLM ควบคุม mouse/keyboard ทุก action

ให้แบ่งเป็น 3 ระดับ:

```text
Screenshot
    ↓
Computer Vision
    ↓
Structured Game State
    ↓
State Machine
    ↓
LLM Planner
    ↓
Action Controller
```

### Vision

รับผิดชอบ:

- ตรวจจับตัวละคร
- ตรวจจับศัตรู
- อ่าน HP/MP
- อ่าน inventory
- อ่าน map/location
- ตรวจจับหน้าต่างหรือ dialog ที่สำคัญ

### State Machine

รับผิดชอบ action ที่ deterministic และเร็ว:

```text
FARM
 ├─ enemy detected → COMBAT
 ├─ loot available → LOOT
 ├─ low HP → HEAL
 ├─ inventory full → TOWN
 └─ stuck → RECOVER
```

### LLM

รับผิดชอบ strategic decision เช่น:

- เลือก map
- เลือก monster
- เปลี่ยน farming strategy
- เลือกว่าจะกลับเมืองหรือไม่
- วิเคราะห์ performance

---

## 4. Game State

Vision Layer ควรแปลง screenshot เป็น structured state:

```json
{
  "location": "Map A",
  "character_hp": 0.82,
  "character_mp": 0.61,
  "target": "Monster X",
  "target_distance": 14,
  "inventory": 0.73,
  "enemy_count": 2,
  "dead": false,
  "stuck": false
}
```

ไม่ควรส่ง screenshot ดิบให้ LLM ทุกครั้ง เพราะ latency และ VRAM สูงเกินความจำเป็น

---

## 5. Combat State Machine

ตัวอย่าง:

```text
              ┌────────────┐
              │   FARMING  │
              └─────┬──────┘
                    │
              enemy detected
                    │
                    ▼
              ┌────────────┐
              │   TARGET   │
              └─────┬──────┘
                    │
                    ▼
              ┌────────────┐
              │   ATTACK   │
              └─────┬──────┘
                    │
              enemy defeated
                    │
                    ▼
              ┌────────────┐
              │    LOOT    │
              └─────┬──────┘
                    │
                    ▼
                  FARMING
```

HP safety check ต้องทำก่อน action สำคัญ:

```text
HP < threshold
    ↓
HEAL / POTION
```

---

## 6. Farming Loop

```text
START
  ↓
ตรวจสถานะ
  ↓
เดินไป farming area
  ↓
ค้นหา enemy
  ↓
เลือก target
  ↓
combat
  ↓
loot
  ↓
ตรวจ HP/MP
  ↓
ตรวจ inventory
  │
  ├── ยังว่าง → FARM ต่อ
  │
  └── เต็ม → RETURN TOWN
                   ↓
                SELL/STORE
                   ↓
                RETURN FARM
```

---

## 7. Memory

ควรเก็บ game memory แยกจาก conversation memory:

```json
{
  "farm_location": "Map A",
  "monster": "Monster X",
  "xp_per_hour": 125000,
  "gold_per_hour": 8200,
  "death_rate": 0.02
}
```

สามารถใช้ SQLite ใน prototype และ PostgreSQL เมื่อระบบใหญ่ขึ้น

---

## 8. Performance Logging

ทุก action ควรบันทึก:

```text
timestamp
state
action
result
xp_delta
gold_delta
hp
mp
inventory
location
```

ตัวอย่าง:

```json
{
  "state": "COMBAT",
  "action": "ATTACK",
  "result": "KILL",
  "xp_delta": 120,
  "gold_delta": 15
}
```

จากนั้นคำนวณ:

```text
XP/hour
Gold/hour
Kills/hour
Death/hour
Potion cost/hour
Repair cost/hour
Net profit/hour
```

---

## 9. Learning

ไม่จำเป็นต้อง train model ตั้งแต่แรก

เริ่มจาก:

```text
VLM
+
LLM
+
State Machine
```

จากนั้นเก็บข้อมูล:

```text
Screenshot
State
Action
Result
Reward
```

เมื่อมีข้อมูลมากขึ้น สามารถทำ:

```text
Imitation Learning
        ↓
Behavior Cloning
        ↓
Fine-tuning / RL
```

เป้าหมายคือให้ model เรียนรู้ policy ที่เร็วกว่า LLM reasoning ทุกครั้ง

---

## 10. Hardware

### RTX 5090

เหมาะสำหรับ local AI agent เพราะสามารถแบ่ง workload ระหว่าง:

```text
RTX 5090 32GB
 ├── Vision Model
 ├── LLM
 ├── Embedding
 └── Game
```

สำหรับ prototype ไม่จำเป็นต้องมีหลาย GPU

---

## 11. Suggested Software Stack

| Component | Technology |
|---|---|
| Vision | Qwen-VL / Qwen2.5-VL หรือรุ่นใหม่ที่เหมาะสม |
| LLM | Qwen3 หรือโมเดล reasoning ขนาดเหมาะสม |
| Agent | Python |
| State | Pydantic |
| Database | SQLite → PostgreSQL |
| Vision Processing | OpenCV |
| Screen Capture | DXGI / platform capture API |
| API | FastAPI |
| Dashboard | React |
| GPU | RTX 5090 |
| Runtime | PyTorch / CUDA |

---

## 12. Recommended Project Structure

```text
mmorpg-ai-agent/
├── app/
│   ├── vision/
│   │   ├── detector.py
│   │   ├── ocr.py
│   │   └── state.py
│   │
│   ├── agent/
│   │   ├── planner.py
│   │   ├── memory.py
│   │   └── policy.py
│   │
│   ├── state_machine/
│   │   ├── states.py
│   │   ├── combat.py
│   │   ├── farming.py
│   │   └── recovery.py
│   │
│   ├── controller/
│   │   ├── keyboard.py
│   │   └── mouse.py
│   │
│   ├── metrics/
│   │   ├── xp.py
│   │   ├── gold.py
│   │   └── performance.py
│   │
│   └── main.py
│
├── models/
├── config/
├── data/
├── logs/
└── README.md
```

---

## 13. Development Milestones

### M1 — Vision

AI สามารถ:

- [ ] ตรวจจับตัวละคร
- [ ] ตรวจจับ enemy
- [ ] อ่าน HP/MP
- [ ] อ่าน inventory
- [ ] ตรวจจับ location

### M2 — Movement

- [ ] เดินไปจุดที่กำหนด
- [ ] ตรวจจับว่าเดินถึงหรือยัง
- [ ] ตรวจจับ stuck
- [ ] recovery จาก stuck

### M3 — Combat

- [ ] Detect enemy
- [ ] Target
- [ ] Attack
- [ ] Heal
- [ ] Loot
- [ ] ตรวจจับ death

### M4 — Farming

- [ ] Farming loop
- [ ] Inventory management
- [ ] Return town
- [ ] Sell/store
- [ ] Return farming area

### M5 — AI Planner

- [ ] เลือก farming location
- [ ] เลือก target
- [ ] เลือก strategy
- [ ] วิเคราะห์ XP/hour
- [ ] วิเคราะห์ Gold/hour

### M6 — Learning

- [ ] เก็บ gameplay dataset
- [ ] เก็บ state/action/result
- [ ] Behavior cloning
- [ ] Fine-tuning
- [ ] Policy optimization

---

## 14. Recommended Agent Design

สุดท้ายระบบควรเป็น:

```text
                  ┌───────────────┐
                  │      LLM      │
                  │ Strategic AI  │
                  └───────┬───────┘
                          │
                  High-level goals
                          │
                          ▼
                  ┌───────────────┐
                  │ State Machine │
                  └───────┬───────┘
                          │
       ┌──────────────────┼──────────────────┐
       ▼                  ▼                  ▼
    Combat            Navigation         Inventory
       │                  │                  │
       ▼                  ▼                  ▼
      CV                 CV                 CV
       │                  │                  │
       └──────────────────┼──────────────────┘
                          ▼
                  Action Controller
                          │
                          ▼
                        Game
```

### หลักการ

**Fast loop**

```text
CV → State → Action
```

ใช้สำหรับ combat และ movement

**Slow loop**

```text
State → LLM → Strategy
```

ใช้สำหรับการวางแผนระดับสูง

แนวทางนี้จะเร็วกว่าและใช้ GPU/LLM น้อยกว่าการให้ VLM + LLM วิเคราะห์ screenshot ทุก action
