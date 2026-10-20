import contextlib
import os
import sqlite3
import time
from typing import Dict, List, Optional, Any


class MemoryDB:
    """
    SQLite telemetry engine for MapleStory performance analytics.
    Stores frame-by-frame state transitions, combat kills, EXP & meso deltas,
    and calculates EXP/hr, Mesos/hr, and kill efficiency.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, "maple_telemetry.db")

        self.db_path = db_path
        self._init_db()

        self.start_time = time.time()
        self.session_kills = 0
        self.session_runes_solved = 0
        self.session_runes_failed = 0
        self.channel_changes = 0

    @contextlib.contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    state TEXT,
                    action TEXT,
                    minimap_x INTEGER,
                    minimap_y INTEGER,
                    exp_delta REAL,
                    meso_delta INTEGER,
                    hp_ratio REAL,
                    mp_ratio REAL,
                    channel INTEGER
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rune_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    duration REAL,
                    success INTEGER,
                    arrows TEXT
                )
                """
            )
            conn.commit()

    def record_telemetry(
        self,
        state: str,
        action: str,
        minimap_pos: Optional[List[int]],
        hp_ratio: float,
        mp_ratio: float,
        channel: int = 1,
        exp_delta: float = 0.0,
        meso_delta: int = 0,
    ):
        mx = minimap_pos[0] if minimap_pos and len(minimap_pos) > 0 else 0
        my = minimap_pos[1] if minimap_pos and len(minimap_pos) > 1 else 0

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO telemetry (
                    timestamp, state, action, minimap_x, minimap_y,
                    exp_delta, meso_delta, hp_ratio, mp_ratio, channel
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (time.time(), state, action, mx, my, exp_delta, meso_delta, hp_ratio, mp_ratio, channel),
            )
            conn.commit()

    def record_rune_event(self, duration: float, success: bool, arrows: List[str]):
        if success:
            self.session_runes_solved += 1
        else:
            self.session_runes_failed += 1

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO rune_events (timestamp, duration, success, arrows)
                VALUES (?, ?, ?, ?)
                """,
                (time.time(), duration, 1 if success else 0, ",".join(arrows)),
            )
            conn.commit()

    def record_kill(self, count: int = 1):
        self.session_kills += count

    def record_channel_change(self):
        self.channel_changes += 1

    def get_summary_metrics(self) -> Dict[str, Any]:
        """
        Calculates session summary rates.
        """
        elapsed_sec = max(1.0, time.time() - self.start_time)
        elapsed_hr = elapsed_sec / 3600.0
        elapsed_min = elapsed_sec / 60.0

        kills_per_min = self.session_kills / elapsed_min
        kills_per_hr = self.session_kills / elapsed_hr

        total_runes = self.session_runes_solved + self.session_runes_failed
        rune_success_rate = (self.session_runes_solved / total_runes) if total_runes > 0 else 1.0

        return {
            "session_duration_sec": int(elapsed_sec),
            "session_kills": self.session_kills,
            "kills_per_minute": round(kills_per_min, 1),
            "kills_per_hour": int(kills_per_hr),
            "runes_solved": self.session_runes_solved,
            "rune_success_rate": round(rune_success_rate * 100, 1),
            "channel_swaps": self.channel_changes,
        }
