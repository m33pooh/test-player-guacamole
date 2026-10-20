import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from config.settings import get_default_config


@dataclass
class ActionLogEntry:
    timestamp: float = field(default_factory=time.time)
    state: str = "UNKNOWN"
    action: str = "IDLE"
    result: str = "SUCCESS"
    xp_delta: int = 0
    gold_delta: int = 0
    hp: float = 1.0
    mp: float = 1.0
    inventory: float = 0.0
    location: str = "Field"
    extra: Dict[str, Any] = field(default_factory=dict)


class MetricsTracker:
    """
    Performance and Action Telemetry Logger matching Section 8 of AI_MORPG_Farming_Agent.md
    Logs:
    - timestamp, state, action, result, xp_delta, gold_delta, hp, mp, inventory, location.
    """
    def __init__(self, log_file: Optional[str] = None):
        if log_file is None:
            config = get_default_config()
            log_file = os.path.join(config.logs_dir, "action_telemetry.jsonl")
        self.log_file = log_file
        self.entries: List[ActionLogEntry] = []
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)

    def log_action(
        self,
        state: str,
        action: str,
        result: str = "SUCCESS",
        xp_delta: int = 0,
        gold_delta: int = 0,
        hp: float = 1.0,
        mp: float = 1.0,
        inventory: float = 0.0,
        location: str = "Field",
        extra: Optional[Dict[str, Any]] = None,
    ):
        entry = ActionLogEntry(
            timestamp=time.time(),
            state=state,
            action=action,
            result=result,
            xp_delta=xp_delta,
            gold_delta=gold_delta,
            hp=round(hp, 3),
            mp=round(mp, 3),
            inventory=round(inventory, 3),
            location=location,
            extra=extra or {},
        )
        self.entries.append(entry)

        # Write to JSONL
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(entry)) + "\n")
        except Exception:
            pass
