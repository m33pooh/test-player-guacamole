import time
from typing import Any, Dict, Optional

from app.metrics.tracker import MetricsTracker


class PerformanceAnalyzer:
    """
    Calculates MMORPG Farming Efficiency Metrics:
    - XP/hour
    - Gold/hour
    - Kills/hour
    - Death/hour
    - Net profit/hour
    """
    def __init__(self, tracker: MetricsTracker):
        self.tracker = tracker
        self.session_start_time = time.time()
        self.total_xp_gained = 0
        self.total_gold_gained = 0
        self.total_kills = 0
        self.total_deaths = 0
        self.total_potions_used = 0

    def add_xp(self, amount: int):
        self.total_xp_gained += amount

    def add_gold(self, amount: int):
        self.total_gold_gained += amount

    def add_kill(self):
        self.total_kills += 1

    def add_death(self):
        self.total_deaths += 1

    def add_potion(self):
        self.total_potions_used += 1

    def get_summary(self) -> Dict[str, Any]:
        elapsed_seconds = max(1.0, time.time() - self.session_start_time)
        hours = elapsed_seconds / 3600.0

        xp_per_hour = self.total_xp_gained / hours
        gold_per_hour = self.total_gold_gained / hours
        kills_per_hour = self.total_kills / hours
        deaths_per_hour = self.total_deaths / hours

        return {
            "session_duration_minutes": round(elapsed_seconds / 60.0, 2),
            "total_xp": self.total_xp_gained,
            "total_gold": self.total_gold_gained,
            "total_kills": self.total_kills,
            "total_deaths": self.total_deaths,
            "total_potions": self.total_potions_used,
            "xp_per_hour": round(xp_per_hour, 0),
            "gold_per_hour": round(gold_per_hour, 0),
            "kills_per_hour": round(kills_per_hour, 1),
            "deaths_per_hour": round(deaths_per_hour, 2),
        }

    def print_summary_report(self):
        summary = self.get_summary()
        print("\n" + "=" * 50)
        print(" MMORPG Farming Agent - Performance Report")
        print("=" * 50)
        print(f" Duration:        {summary['session_duration_minutes']} minutes")
        print(f" Total Kills:     {summary['total_kills']} ({summary['kills_per_hour']} / hr)")
        print(f" Total Deaths:    {summary['total_deaths']} ({summary['deaths_per_hour']} / hr)")
        print(f" Total EXP:       {summary['total_xp']} ({summary['xp_per_hour']} EXP / hr)")
        print(f" Total Gold:      {summary['total_gold']} ({summary['gold_per_hour']} Gold / hr)")
        print(f" Potions Used:    {summary['total_potions']}")
        print("=" * 50 + "\n")
