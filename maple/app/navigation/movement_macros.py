import time
from typing import Optional
from maple.app.controller.input_driver import GuacamoleInputDriver


class MovementMacros:
    """
    Class-specific movement and skill animation canceling macros.
    Executes precise movement chains based on Archetype:
    - Teleport Casting (Mages / Bishop): Teleport + Attack combo
    - Flash Jump + Dash (Thieves / Archers): Dual jump + projectile throw
    - Super Jump (Buccaneer): Fast momentum glide across platforms
    - Up-Jump / Rope Lift: Vertical platform ascension
    """

    def __init__(self, driver: GuacamoleInputDriver):
        self.driver = driver

    def teleport_cast(
        self,
        direction: str,
        teleport_key: str = "Shift",
        attack_key: Optional[str] = "Ctrl",
        vertical: Optional[str] = None,
    ):
        """
        Executes Mage Teleport Casting with Animation Canceling:
        Direction + Teleport + Attack triggered within 20-40ms.
        """
        dir_key = "ArrowLeft" if direction.lower() == "left" else "ArrowRight"
        if vertical == "up":
            dir_key = "ArrowUp"
        elif vertical == "down":
            dir_key = "ArrowDown"

        # Press direction, teleport, and optional attack together
        if self.driver.page is not None:
            try:
                self.driver.page.keyboard.down(dir_key)
                self.driver.page.keyboard.down(teleport_key)
                time.sleep(0.04)
                if attack_key:
                    self.driver.page.keyboard.down(attack_key)
                    time.sleep(0.03)
                    self.driver.page.keyboard.up(attack_key)
                self.driver.page.keyboard.up(teleport_key)
                self.driver.page.keyboard.up(dir_key)
            except Exception as e:
                print(f"[MovementMacros Error] Teleport cast error: {e}", flush=True)
        else:
            print(f"[MovementMacros Sim] Teleport Cast: {dir_key} + {teleport_key} + {attack_key}", flush=True)

    def flash_jump_attack(
        self,
        direction: str,
        jump_key: str = "Alt",
        attack_key: Optional[str] = "q",
    ):
        """
        Executes Flash Jump into instant skill cast for Projectile Assassins / Archers.
        """
        self.driver.flash_jump(direction=direction, jump_key=jump_key, attack_key=attack_key)

    def buccaneer_super_jump(
        self,
        direction: str,
        dash_key: str = "Shift",
        jump_key: str = "Alt",
    ):
        """
        Executes Buccaneer Super Jump (Dash momentum cancel into jump).
        """
        dir_key = "ArrowLeft" if direction.lower() == "left" else "ArrowRight"
        if self.driver.page is not None:
            try:
                self.driver.page.keyboard.down(dir_key)
                time.sleep(0.02)
                self.driver.press_key(dash_key, duration=0.03)
                time.sleep(0.02)
                self.driver.press_key(jump_key, duration=0.04)
                self.driver.page.keyboard.up(dir_key)
            except Exception as e:
                print(f"[MovementMacros Error] Super jump error: {e}", flush=True)
        else:
            print(f"[MovementMacros Sim] Super Jump {direction} ({dash_key} -> {jump_key})", flush=True)

    def down_jump(self, jump_key: str = "Alt"):
        """
        Drops down to lower platform.
        """
        self.driver.down_jump(jump_key=jump_key)

    def rope_lift(self, rope_key: str = "v"):
        """
        Ascends using 5th job Rope Lift.
        """
        self.driver.rope_lift(rope_key=rope_key)
