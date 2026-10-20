import random
import time
from typing import Tuple


class GaussianTimingJitter:
    """
    Gaussian Timing Jitter engine.
    Produces human-like keypress durations, release latencies, and interval pauses
    using normal (Gaussian) distributions with bounds checking to avoid detection.
    """

    def __init__(
        self,
        default_press_mean: float = 0.065,
        default_press_std: float = 0.015,
        min_press: float = 0.025,
        max_press: float = 0.140,
    ):
        self.default_press_mean = default_press_mean
        self.default_press_std = default_press_std
        self.min_press = min_press
        self.max_press = max_press

    def get_press_duration(
        self,
        mean: float = None,
        std: float = None,
        bounds: Tuple[float, float] = None,
    ) -> float:
        """
        Calculates a randomized key down duration in seconds.
        """
        m = mean if mean is not None else self.default_press_mean
        s = std if std is not None else self.default_press_std
        lower, upper = bounds if bounds is not None else (self.min_press, self.max_press)

        duration = random.gauss(m, s)
        return max(lower, min(upper, duration))

    def get_interval_delay(
        self,
        mean: float = 0.050,
        std: float = 0.012,
        min_val: float = 0.020,
        max_val: float = 0.120,
    ) -> float:
        """
        Calculates pause time between successive keystrokes.
        """
        delay = random.gauss(mean, std)
        return max(min_val, min(max_val, delay))

    def sleep_jitter(self, mean: float, std: float = None, min_val: float = 0.01):
        """
        Sleeps for a duration sampled from Gaussian distribution.
        """
        if std is None:
            std = mean * 0.20
        duration = max(min_val, random.gauss(mean, std))
        time.sleep(duration)
        return duration
