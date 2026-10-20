import time
from typing import Dict, List, Optional, Any


class BuffSynchronizer:
    """
    Multiplier & Rune Synchronization Engine (Section 5.4).
    Synchronizes Rune solving with EXP multipliers (2x/3x coupon, MVP, Gold Potion)
    and Full Map Attacks (FMAs) to maximize kill yield during the +100% EXP window.
    """

    def __init__(self, fma_cooldown_sec: float = 60.0):
        self.fma_cooldown_sec = fma_cooldown_sec
        self.last_fma_cast_time = 0.0

        self.exp_coupon_expires_at = time.time() + 1800.0  # Default 30 min
        self.mvp_buff_expires_at = time.time() + 1800.0

    def record_fma_used(self):
        self.last_fma_cast_time = time.time()

    def should_delay_rune_for_fma(self, tolerance_sec: float = 12.0) -> bool:
        """
        If a large screen-clearing burst skill will be ready in < tolerance_sec,
        recommends holding Rune solve briefly to activate during the burst.
        """
        now = time.time()
        time_until_fma = max(0.0, self.fma_cooldown_sec - (now - self.last_fma_cast_time))
        if 0.0 < time_until_fma <= tolerance_sec:
            print(f"[BuffSynchronizer] Holding Rune for {time_until_fma:.1f}s until Full Map Attack (FMA) is ready!", flush=True)
            return True
        return False

    def is_exp_coupon_active(self) -> bool:
        return time.time() < self.exp_coupon_expires_at
