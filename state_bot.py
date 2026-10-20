"""
VLM-Powered State Machine Bot
Sends screenshot to Qwen VLM at http://127.0.0.1:8888/v1 for state detection.

States:
  UNKNOWN  -> ask VLM what state we are in
  DEAD     -> click Respawn In Town
  IN_TOWN  -> open World Map via Map tab button (no wandering)
  OPEN_MAP -> verify map opened, retry if not
  WARP     -> double-click Stormreef Isle zone
  IN_FIELD -> navigate via VLM + OpenCV minimap dots
  COMBAT   -> attack with skill rotation
"""

import os
import sys
import json
import base64
import time
import io

import cv2
import numpy as np
import requests

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GUACAMOLE_URL = os.getenv(
    "GUACAMOLE_URL",
    "http://localhost:60289/guacamole/#/client/UkRQIENvbm5lY3Rpb24AYwBkZWZhdWx0",
)
VLM_ENDPOINT = "http://127.0.0.1:8888/v1"
VLM_MODEL = None

_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env):
    with open(_env) as _f:
        for _l in _f:
            _l = _l.strip()
            if _l and not _l.startswith("#") and "=" in _l:
                _k, _v = _l.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip("'\""))

VLM_API_KEY = os.getenv("UNSLOTH_API_KEY", "")

# UI coords (viewport 1707x932)
RESPAWN_COORDS = [(853, 725), (853, 720), (853, 730), (744, 590), (853, 590)]
MAP_TAB_X, MAP_TAB_Y = 68, 761
MMICON_X, MMICON_Y = 1418, 202
# Stormreef Isle (Lv61-65) exact verified coordinates on World Map
STORMREEF_X = 455
STORMREEF_Y = 430
# Green Warp button at bottom right of World Map
WARP_BTN_X = 1620
WARP_BTN_Y = 915
MM_X1, MM_Y1, MM_X2, MM_Y2 = 1295, 10, 1481, 220

# ---------------------------------------------------------------------------
# VLM helpers
# ---------------------------------------------------------------------------


def _vlm_model():
    global VLM_MODEL
    if VLM_MODEL:
        return VLM_MODEL
    try:
        h = {"Authorization": f"Bearer {VLM_API_KEY}"} if VLM_API_KEY else {}
        r = requests.get(f"{VLM_ENDPOINT}/models", headers=h, timeout=3)
        if r.status_code == 200:
            data = r.json().get("data", [])
            if data:
                VLM_MODEL = data[0]["id"]
                print(f"[VLM] model={VLM_MODEL}", flush=True)
                return VLM_MODEL
    except Exception as e:
        print(f"[VLM] model detect: {e}", flush=True)
    VLM_MODEL = "default"
    return VLM_MODEL


def frame_to_b64(frame, max_w=960):
    h, w = frame.shape[:2]
    if w > max_w:
        frame = cv2.resize(frame, (max_w, int(h * max_w / w)))
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).save(
        buf, format="JPEG", quality=65
    )
    return base64.b64encode(buf.getvalue()).decode()


def ask_vlm(frame, prompt, max_tokens=250):
    model = _vlm_model()
    b64 = frame_to_b64(frame)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {VLM_API_KEY}",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            }
        ],
        "max_tokens": max_tokens,
        "temperature": 0.1,
    }
    try:
        t0 = time.time()
        r = requests.post(
            f"{VLM_ENDPOINT}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        lat = round(time.time() - t0, 2)
        if r.status_code == 200:
            raw = r.json()["choices"][0]["message"]["content"].strip()
            print(f"[VLM {lat}s] {raw[:200]}", flush=True)
            cleaned = raw
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0]
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0]
            try:
                return json.loads(cleaned.strip())
            except json.JSONDecodeError:
                return {"raw": raw, "error": "json_parse_failed"}
        print(f"[VLM] HTTP {r.status_code}", flush=True)
        return {"error": f"http_{r.status_code}"}
    except requests.Timeout:
        print("[VLM] timeout", flush=True)
        return {"error": "timeout"}
    except Exception as e:
        print(f"[VLM] {e}", flush=True)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

STATE_PROMPT = (
    "You are an AI agent playing an MMORPG.\n"
    "Analyze this screenshot. Reply ONLY with valid JSON, no markdown:\n"
    "{\n"
    '  "state": "<dead|in_town|world_map_open|in_field|in_combat>",\n'
    '  "hp_ratio": <float 0.0-1.0>,\n'
    '  "monsters_visible": <true/false>,\n'
    '  "minimap_has_red_dots": <true/false>,\n'
    '  "teleport_crystal_visible": <true/false>,\n'
    '  "world_map_open": <true/false>,\n'
    '  "reasoning": "<one sentence>"\n'
    "}\n"
    "State clues:\n"
    "- dead: dark center dialog with Respawn In Town button\n"
    "- in_town: town area, minimap mostly green, no red monster dots\n"
    "- world_map_open: large map overlay with zone labels covers screen\n"
    "- in_field: outdoor zone, minimap top-right has red monster dots\n"
    "- in_combat: red HP bars visible above monsters on main screen"
)

FIELD_PROMPT = (
    "You are an AI agent controlling an MMORPG Gunslinger.\n"
    "Minimap is TOP-RIGHT corner (full-screenshot x:1295-1481 y:10-220). Red=monsters.\n"
    "Reply ONLY valid JSON:\n"
    "{\n"
    '  "nearest_monster_x": <int or null>,\n'
    '  "nearest_monster_y": <int or null>,\n'
    '  "nearest_dot_x": <int or null in full-screenshot coords>,\n'
    '  "nearest_dot_y": <int or null>,\n'
    '  "hp_critical": <true/false>,\n'
    '  "action": "<click_minimap_dot|attack_monster|use_potion|rotate_camera>",\n'
    '  "reasoning": "<brief>"\n'
    "}"
)

CRYSTAL_PROMPT = (
    "Analyze this MMORPG game screenshot. "
    "Find the glowing BLUE Teleport Crystal - a tall blue glowing pillar/monument in the town center near the fountain. "
    "Players double-click it to open the World Map teleport menu. "
    "Reply ONLY with valid JSON: "
    '{"crystal_visible": true/false, '
    '"crystal_x": <int CSS-pixel x center of crystal in this 1707x932 image or null>, '
    '"crystal_y": <int CSS-pixel y center or null>, '
    '"crystal_description": "<brief where>"}'
)

# ---------------------------------------------------------------------------
# OpenCV fallbacks (fast, no VLM needed)
# ---------------------------------------------------------------------------


def cv_red_dot(frame):
    mm = frame[MM_Y1:MM_Y2, MM_X1:MM_X2]
    if mm.size == 0:
        return None
    hsv = cv2.cvtColor(mm, cv2.COLOR_BGR2HSV)
    m = cv2.bitwise_or(
        cv2.inRange(hsv, (0, 120, 100), (10, 255, 255)),
        cv2.inRange(hsv, (170, 120, 100), (180, 255, 255)),
    )
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    pcx, pcy = mm.shape[1] // 2, mm.shape[0] // 2
    best, bd = None, float("inf")
    for c in cnts:
        if cv2.contourArea(c) < 3:
            continue
        M = cv2.moments(c)
        if M["m00"] == 0:
            continue
        cx, cy = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
        d = ((cx - pcx) ** 2 + (cy - pcy) ** 2) ** 0.5
        if d < bd:
            bd, best = d, (MM_X1 + cx, MM_Y1 + cy)
    return best


def cv_enemy(frame):
    h, w = frame.shape[:2]
    roi = frame[int(h * 0.1) : int(h * 0.7), int(w * 0.15) : int(w * 0.85)]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    m = cv2.bitwise_or(
        cv2.inRange(hsv, (0, 150, 150), (8, 255, 255)),
        cv2.inRange(hsv, (172, 150, 150), (180, 255, 255)),
    )
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cx_c, cy_c = w // 2, h // 2
    best, bd = None, float("inf")
    for c in cnts:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw < 15 or cw > 120 or ch < 3 or ch > 15 or cw / ch < 2.0:
            continue
        vx = x + int(w * 0.15) + cw // 2
        vy = y + int(h * 0.1) + ch // 2
        d = ((vx - cx_c) ** 2 + (vy - cy_c) ** 2) ** 0.5
        if d < bd:
            bd, best = d, (vx, vy)
    return best


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------


class S:
    UNKNOWN = "UNKNOWN"
    DEAD = "DEAD"
    IN_TOWN = "IN_TOWN"
    OPEN_MAP = "OPEN_MAP"
    WARP = "WARP"
    IN_FIELD = "IN_FIELD"
    COMBAT = "COMBAT"


# ---------------------------------------------------------------------------
# Bot
# ---------------------------------------------------------------------------


class Bot:
    def __init__(self):
        self.state = S.UNKNOWN
        self.cd = {}           # cooldown timestamps
        self.rotdir = 1
        self.loop = 0

    # ---- helpers ----

    def cap(self, page):
        try:
            d = page.screenshot(type="jpeg", quality=65, timeout=2500)
            return cv2.imdecode(np.frombuffer(d, np.uint8), cv2.IMREAD_COLOR)
        except Exception as e:
            print(f"[Cap] {e}", flush=True)
            return None

    def click(self, p, x, y):
        p.mouse.click(x, y)

    def dbl(self, p, x, y):
        p.mouse.dblclick(x, y)

    def key(self, p, k, d=0.03):
        p.keyboard.press(k)
        time.sleep(d)

    def log(self, m):
        print(f"[{self.state}] {m}", flush=True)

    # ---- UNKNOWN ----

    def do_unknown(self, p, f):
        if f is None:
            time.sleep(1)
            return
        v = ask_vlm(f, STATE_PROMPT, 200)
        s = v.get("state", "").lower()
        self.log(f"VLM state={s!r} | {v.get('reasoning', '')}")
        if "dead" in s:
            self.state = S.DEAD
        elif "world_map" in s or v.get("world_map_open"):
            self.state = S.WARP
        elif "town" in s:
            self.state = S.IN_TOWN
        elif "combat" in s:
            self.state = S.COMBAT
        elif "field" in s:
            self.state = S.IN_FIELD
        else:
            if cv_enemy(f):
                self.state = S.COMBAT
            elif cv_red_dot(f):
                self.state = S.IN_FIELD
            else:
                self.state = S.IN_TOWN

    # ---- DEAD ----

    def do_dead(self, p, f):
        self.log("Player DEAD. Clicking Respawn In Town...")
        self.click(p, 853, 725)
        time.sleep(0.3)
        self.click(p, 853, 725)
        time.sleep(0.3)
        self.key(p, "Enter")
        time.sleep(0.2)
        self.key(p, "Space")
        time.sleep(0.2)
        for bx, by in RESPAWN_COORDS:
            self.click(p, bx, by)
            time.sleep(0.15)
        self.log("Waiting 4s for town load...")
        time.sleep(4.0)
        self.state = S.IN_TOWN

    # ---- IN_TOWN ----

    def do_in_town(self, p, f):
        """Interact with Teleport Crystal to open the Teleport World Map.
        
        Strategy:
        1. Walk/click towards Teleport Crystal in town (x=1100, y=400 or VLM detected crystal).
        2. Double click crystal / press F to open Teleport World Map.
        3. Verify World Map with Warp button is open.
        """
        self.log("IN TOWN. Interacting with Teleport Crystal...")
        self.key(p, "Escape")
        time.sleep(0.3)

        # Step 1: Click crystal area to walk & interact
        self.click(p, 1100, 400)
        time.sleep(1.5)
        self.dbl(p, 1100, 400)
        time.sleep(0.5)
        self.key(p, "f")
        time.sleep(2.0)

        f2 = self.cap(p)
        if f2 is not None:
            v2 = ask_vlm(f2, STATE_PROMPT, 150)
            self.log(f"VLM after crystal interact: state={v2.get('state')} wm={v2.get('world_map_open')}")
            if v2.get("world_map_open") or "world_map" in v2.get("state", "").lower():
                self.log("Teleport World Map is open!")
                self.state = S.WARP
                return

        # Fallback: VLM locate crystal
        if f is not None:
            vc = ask_vlm(f, CRYSTAL_PROMPT, 150)
            if vc.get("crystal_visible") and vc.get("crystal_x") and vc.get("crystal_y"):
                cx, cy = vc["crystal_x"], vc["crystal_y"]
                self.log(f"Walking to VLM crystal ({cx},{cy})...")
                self.click(p, cx, cy)
                time.sleep(1.5)
                self.dbl(p, cx, cy)
                time.sleep(0.5)
                self.key(p, "f")
                time.sleep(2.0)
                f3 = self.cap(p)
                if f3 is not None:
                    v3 = ask_vlm(f3, STATE_PROMPT, 150)
                    if v3.get("world_map_open") or "world_map" in v3.get("state", "").lower():
                        self.log("Teleport World Map open via VLM crystal!")
                        self.state = S.WARP
                        return

        # Fallback: Press M key
        self.log("Fallback: pressing M...")
        self.click(p, 853, 466)
        time.sleep(0.2)
        self.key(p, "m")
        time.sleep(1.5)
        self.state = S.OPEN_MAP

    # ---- OPEN_MAP ----

    def do_open_map(self, p, f):
        if f is not None:
            v = ask_vlm(f, STATE_PROMPT, 150)
            if v.get("world_map_open") or "world_map" in v.get("state", "").lower():
                self.log("VLM: Map confirmed open.")
                self.state = S.WARP
                return
            self.log(f"Map not open, VLM={v.get('state')}")
        self.state = S.IN_TOWN

    # ---- WARP ----

    def do_warp(self, p, f):
        self.log(f"WARP: Selecting Stormreef Isle (Lv61-65) at ({STORMREEF_X},{STORMREEF_Y})...")
        self.click(p, STORMREEF_X, STORMREEF_Y)
        time.sleep(0.8)
        self.log(f"WARP: Clicking green Warp button at ({WARP_BTN_X},{WARP_BTN_Y})...")
        self.click(p, WARP_BTN_X, WARP_BTN_Y)
        self.log("Waiting 5s for field transition...")
        time.sleep(5.0)
        self.state = S.IN_FIELD

    # ---- IN_FIELD ----

    def do_in_field(self, p, f):
        if f is None:
            time.sleep(0.5)
            return

        # Proactive potion and buff
        self.key(p, "5", 0.02)
        self.key(p, "6", 0.02)

        v = ask_vlm(f, FIELD_PROMPT, 200)
        act = v.get("action", "").lower()
        reason = v.get("reasoning", "").lower()
        self.log(f"VLM action={act} | {v.get('reasoning', '')}")

        # Check death in field
        if "dead" in reason or "respawn" in reason or "dead" in act or "respawn" in act:
            self.log("Death detected in field. Switching to DEAD state.")
            self.state = S.DEAD
            return

        if v.get("hp_critical"):
            self.key(p, "5")
            self.key(p, "5")

        mx, my = v.get("nearest_monster_x"), v.get("nearest_monster_y")
        if mx and my:
            self.log(f"VLM: monster at ({mx},{my}) -> COMBAT")
            self.state = S.COMBAT
            return

        # OpenCV enemy check
        e = cv_enemy(f)
        if e:
            self.log(f"CV: enemy {e} -> COMBAT")
            self.state = S.COMBAT
            return

        if act == "click_minimap_dot":
            dx, dy = v.get("nearest_dot_x"), v.get("nearest_dot_y")
            if dx and dy:
                self.log(f"VLM: minimap dot ({dx},{dy})")
                self.click(p, dx, dy)
                time.sleep(2.0)
                return

        dot = cv_red_dot(f)
        if dot:
            self.log(f"CV: dot {dot}")
            self.click(p, dot[0], dot[1])
            time.sleep(2.0)
        else:
            self.log("No dots. Rotating camera...")
            cx, cy = 853, 466
            ddx = 160 * self.rotdir
            p.mouse.move(cx, cy)
            p.mouse.down(button="right")
            time.sleep(0.08)
            p.mouse.move(cx + ddx, cy, steps=6)
            time.sleep(0.08)
            p.mouse.up(button="right")
            self.rotdir *= -1
            time.sleep(0.5)

    # ---- COMBAT ----

    def do_combat(self, p, f):
        if f is None:
            time.sleep(0.3)
            return
        e = cv_enemy(f)
        if not e:
            self.log("No enemy. -> IN_FIELD")
            self.state = S.IN_FIELD
            return
        tx, ty = e
        px, py = 853, 466
        now = time.time()
        dx, dy = tx - px, ty - py
        dist = max(1.0, (dx ** 2 + dy ** 2) ** 0.5)

        if dist > 220:
            ax = max(160, min(1380, int(px + (dx / dist) * (dist - 180))))
            ay = max(200, min(760, int(py + (dy / dist) * (dist - 180))))
            self.click(p, ax, ay)
            time.sleep(0.15)

        ad = min(dist * 0.4, 140)
        ax = int(px + (dx / dist) * ad)
        ay = int(py + (dy / dist) * ad)
        self.log(f"Attack ({tx},{ty}) AoE ({ax},{ay})")

        self.key(p, "6")
        self.key(p, "5")
        if now - self.cd.get("3", 0) > 4.5:
            p.mouse.move(ax, ay)
            self.key(p, "3")
            self.click(p, ax, ay)
            self.cd["3"] = now
        p.mouse.move(ax, ay)
        self.key(p, "1")
        self.click(p, ax, ay)
        p.mouse.move(tx, ty)
        for k in ["q", "2", "e", "t", "y", "r"]:
            self.key(p, k, 0.025)
            self.click(p, tx, ty)
        p.mouse.move(ax, ay)
        self.key(p, "1")
        self.click(p, ax, ay)

        if now - self.cd.get("vlm", 0) > 15.0:
            v = ask_vlm(f, STATE_PROMPT, 150)
            s = v.get("state", "").lower()
            if "dead" in s:
                self.state = S.DEAD
            elif "town" in s:
                self.state = S.IN_TOWN
            self.cd["vlm"] = now

    # ---- Main ----

    def run(self, duration=0):
        if not HAS_PLAYWRIGHT:
            print("[Error] pip install playwright")
            return
        print(f"=== VLM State Bot === endpoint={VLM_ENDPOINT}", flush=True)
        _vlm_model()
        with sync_playwright() as pw:
            try:
                br = pw.chromium.connect_over_cdp("http://localhost:9222", timeout=5000)
                pg = None
                for ctx in br.contexts:
                    for p2 in ctx.pages:
                        if "guacamole" in p2.url:
                            pg = p2
                            break
                if not pg:
                    pg = br.contexts[0].new_page()
                    pg.goto(GUACAMOLE_URL)
                pg.bring_to_front()
                time.sleep(0.8)
                print(f"[Bot] attached: {pg.url}", flush=True)

                dispatch = {
                    S.DEAD:     self.do_dead,
                    S.IN_TOWN:  self.do_in_town,
                    S.OPEN_MAP: self.do_open_map,
                    S.WARP:     self.do_warp,
                    S.IN_FIELD: self.do_in_field,
                    S.COMBAT:   self.do_combat,
                }
                t0 = time.time()
                while True:
                    self.loop += 1
                    if duration > 0 and time.time() - t0 >= duration:
                        break
                    f = self.cap(pg)
                    print(f"\n{'='*40}\nLoop {self.loop} | {self.state}", flush=True)
                    if self.state == S.UNKNOWN or self.loop % 30 == 0:
                        self.do_unknown(pg, f)
                        continue
                    handler = dispatch.get(self.state)
                    if handler:
                        handler(pg, f)

            except KeyboardInterrupt:
                print("\n[Bot] Stopped (Ctrl+C).", flush=True)
            except Exception as e:
                import traceback
                traceback.print_exc()
            finally:
                print("=== Bot Ended ===", flush=True)


if __name__ == "__main__":
    Bot().run(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
