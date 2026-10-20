# AI MapleStory Farming Agent v2 — Local Architecture & Class Strategies

AI Agent สำหรับเกม 2D Side-Scrolling (MapleStory) ที่รองรับการเชื่อมต่อผ่าน **Apache Guacamole Web Remote** โดยตรงด้วย Playwright / CDP พร้อมสถาปัตยกรรม **Multi-Class Archetype Engine**, **15-Cycle Loot & Refresh Engine**, และ **Dynamic Strategic Optimization (LLM)** ตามข้อกำหนดใน [maplev2.md](file:///c:/Users/asuslap/git/testbb/maple/maplev2.md)

---

## 1. คุณสมบัติใหม่ใน v2 (What's New in v2)

1. **Class Archetype Engine (รองรับ 4 กลุ่มกลไกการฟาร์ม):**
   - **The Teleporters (Bishop, Mage, Luminous):** การทำ Teleport Casting ยกเลิก Animation (Animation Canceling) และการวาร์ปข้ามชั้นแพลตฟอร์มในแนวตั้ง
   - **The Projectile & Mark Assassins (Night Lord, Night Walker, Wind Archer):** กระโดดฟาร์มบริเวณกึ่งกลางแมพ (Center-platform) อาศัยการชิ่งกระจายของ Mark กวาดมอนสเตอร์ทั้งจอ พร้อมวาง Summon ขนาบข้าง
   - **The Micro-Summon / Area Controllers (Lara, Corsair, Kanna):** ตรวจจับ Dragon Veins (น้ำ/ลม/ไฟ) บนพื้นด้วย Vision และสั่งจุดระเบิด Eruption ครอบคลุมทั้งแผนที่ วนรอบทุก 15-18 วินาที
   - **The Active Sweepers & Gauge Managers (Buccaneer, Adele, Dawn Warrior):** Super Jump พุ่งข้ามแมพด้วยโมเมนตัมสูง ควบคู่การอ่าน Energy/Aether Gauge เพื่อคุม Lord of the Deep และ Flying Swords (Order)
2. **15-Cycle Loot Strategy (ระบบบริหารรอบเก็บเงิน):**
   - **รอบที่ 1 - 13 (Kill Focus):** วิ่งและโจมตีด้วยความเร็วสูงสุดในโซนหลัก ไม่แวะมุมแมพ
   - **รอบที่ 14 - 15 (Loot & Refresh Cycle):** เดินอ้อมไปจุดที่วาง Summon (Erda Fountain / Sol Janus) เพื่อเก็บ Meso Bags ที่ตกค้างทั้งหมดก่อนหมดเวลา Despawn (120s) และรีเฟรช Summon ใหม่ในจังหวะเดียวกัน
3. **Multiplier & Rune Synchronization:**
   - หน่วงเวลาการแก้ Rune สั้นๆ หากสกิลกวาดล้างจอใหญ่ (Full Map Attack / Burst FMA) กำลังจะพร้อมใช้งานในไม่กี่วินาที เพื่อรับผลคูณ +100% EXP สูงสุดในช่วงที่มีสกิลใหญ่
4. **One-Shot & Dynamic Summon Optimization (LLM Slow Path):**
   - วิเคราะห์ Kills/min เทียบกับ Max Spawn Limit ของแผนที่เพื่อประเมินสถานะ One-Shot
   - สร้าง Heatmap จากตำแหน่งมอนสเตอร์ที่รอดชีวิต เพื่อขยับจุดวาง Summon (Sol Janus / Erda Fountain) อัตโนมัติ

---

## 2. โครงสร้างโฟลเดอร์ (Project Structure v2)

```text
maple/
├── app/
│   ├── capture/
│   │   ├── guacamole_capture.py    # Playwright CDP Web Remote Screen Capture
│   │   └── dxgi_capture.py         # Capture Fallback (DXGI / mss)
│   ├── controller/
│   │   ├── timing_jitter.py        # Gaussian Timing Jitter จำลองจังหวะการกดแบบมนุษย์
│   │   └── input_driver.py         # ควบคุมคีย์บอร์ด/เมาส์เข้าสู่ Guacamole Canvas
│   ├── vision/
│   │   ├── minimap_tracker.py      # OpenCV ค้นหาจุดเหลือง (ตนเอง), แดง (คนอื่น), ม่วง (Rune)
│   │   ├── status_ocr.py           # คำนวณ HP/MP ratio และสถานะตัวละคร
│   │   ├── class_gauge_reader.py   # อ่านเกจเฉพาะอาชีพ (Lara Veins, Buccaneer Energy, Adele Aether)
│   │   ├── mob_detector.py         # ตรวจจับมอนสเตอร์และ Elite Boss (YOLOv11/HSV)
│   │   ├── rune_solver.py          # ถอดรหัสลูกศร 4 ทิศทางของเสา Rune
│   │   └── vlm_inspector.py        # Qwen-VL ตรวจจับห้องตรวจสอบ / แชท
│   ├── navigation/
│   │   ├── platform_graph.py       # โครงสร้างกราฟแพลตฟอร์ม 2D
│   │   ├── pathfinder.py           # A* Pathfinder คำนวณการเดิน/กระโดด
│   │   └── movement_macros.py      # ท่าเคลื่อนที่เฉพาะทาง (Teleport Cast, Super Jump, Flash Jump)
│   ├── state_machine/
│   │   ├── core_fsm.py             # FSM ตัวจัดการ State หลัก
│   │   ├── archetypes/             # กลไกการฟาร์มเฉพาะกลุ่มอาชีพ
│   │   │   ├── teleporter_fsm.py   # Bishop / Mage
│   │   │   ├── projectile_fsm.py   # Night Lord / Night Walker
│   │   │   ├── summoner_fsm.py     # Lara / Corsair
│   │   │   └── sweeper_fsm.py      # Buccaneer / Adele
│   │   ├── rotation_farm.py        # ตัวควบคุมรอบการเดินวน
│   │   ├── rune_state.py           # ลำดับขั้นตอนการเดินไปแก้รูน
│   │   ├── channel_surfer.py       # ระบบย้ายแนลอัตโนมัติ (Anti-KS)
│   │   └── loot_cycle.py           # ระบบ 15-cycle Loot & Refresh
│   ├── agent/
│   │   ├── memory_db.py            # SQLite Telemetry (Kills/min, EXP/hr, Rune Stats)
│   │   ├── strategic_planner.py    # LLM วางแผน One-Shot และ Summon Heatmap
│   │   ├── buff_synchronizer.py    # ระบบ Sync เวลา Rune กับ Full Map Attack
│   │   └── social_responder.py     # ระบบตอบกลับแชทอัตโนมัติ
│   └── main.py                     # Entry point หลักสำหรับการรัน
├── configs/
│   ├── maps/
│   │   ├── limina_1_4.yaml         # แผนที่ Limina 1-4
│   │   └── carcion_beach_3.yaml    # แผนที่ Carcion: Calm Beach 3
│   └── classes/
│       ├── bishop.yaml             # สาย Teleporter
│       ├── night_lord.yaml         # สาย Projectile Assassin
│       ├── lara.yaml               # สาย Summoner / Area Controller
│       └── buccaneer.yaml          # สาย Sweeper / Super Jump
├── tests/
│   └── test_components.py          # ชุดทดสอบ Unit Tests (ผ่าน 12/12 รายการ)
└── README.md
```

---

## 3. ตัวอย่างการสั่งรันตามอาชีพ (Usage Examples)

### 3.1 Bishop (The Teleporters) บนแผนที่ Carcion Beach 3
```bash
python maple/app/main.py --cdp-url http://localhost:9222 --class-config maple/configs/classes/bishop.yaml --map maple/configs/maps/carcion_beach_3.yaml
```

### 3.2 Night Lord (Projectile & Mark Assassin) บนแผนที่ Limina 1-4
```bash
python maple/app/main.py --cdp-url http://localhost:9222 --class-config maple/configs/classes/night_lord.yaml --map maple/configs/maps/limina_1_4.yaml
```

### 3.3 Lara (Micro-Summon / Dragon Vein Controller)
```bash
python maple/app/main.py --cdp-url http://localhost:9222 --class-config maple/configs/classes/lara.yaml
```

### 3.4 Buccaneer (Active Sweeper / Super Jump)
```bash
python maple/app/main.py --cdp-url http://localhost:9222 --class-config maple/configs/classes/buccaneer.yaml
```

### 3.5 รันโหมดจำลอง (Simulation Mode)
```bash
python maple/app/main.py --simulate --class-config maple/configs/classes/bishop.yaml --duration 30
```
