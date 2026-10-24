import unittest
from maple.app.controller.timing_jitter import GaussianTimingJitter
from maple.app.controller.input_driver import GuacamoleInputDriver, get_vk_code, VK_MAP


class TestTimingJitter(unittest.TestCase):

    def setUp(self):
        self.jitter = GaussianTimingJitter()

    def test_press_duration_within_bounds(self):
        for _ in range(50):
            d = self.jitter.get_press_duration(mean=0.075, std=0.012, bounds=(0.04, 0.12))
            self.assertGreaterEqual(d, 0.04)
            self.assertLessEqual(d, 0.12)

    def test_interval_delay_within_bounds(self):
        for _ in range(50):
            d = self.jitter.get_interval_delay(mean=0.080, std=0.015, min_val=0.03, max_val=0.15)
            self.assertGreaterEqual(d, 0.03)
            self.assertLessEqual(d, 0.15)


class TestInputDriver(unittest.TestCase):

    def setUp(self):
        self.driver = GuacamoleInputDriver()

    def test_vk_mapping(self):
        self.assertEqual(get_vk_code("left"), 0x25)
        self.assertEqual(get_vk_code("arrowleft"), 0x25)
        self.assertEqual(get_vk_code("right"), 0x27)
        self.assertEqual(get_vk_code("arrowright"), 0x27)
        self.assertEqual(get_vk_code("up"), 0x26)
        self.assertEqual(get_vk_code("down"), 0x28)
        self.assertEqual(get_vk_code("space"), 0x20)
        self.assertEqual(get_vk_code("alt"), 0x12)
        self.assertEqual(get_vk_code("ctrl"), 0x11)
        self.assertEqual(get_vk_code("pagedown"), 0x22)
        # Single characters
        self.assertEqual(get_vk_code("q"), ord("Q"))
        self.assertEqual(get_vk_code("1"), ord("1"))

    def test_driver_without_page_or_hwnd(self):
        # Driver should safely execute simulation mode without throwing exceptions
        self.driver.press_key("alt", duration=0.01)
        self.driver.tap_key("space")
        self.driver.walk("left", duration=0.01)
        self.driver.flash_jump("right", jump_key="alt", attack_key="ctrl")
        self.driver.down_jump(jump_key="alt")
        self.driver.press_combo(["ArrowDown", "alt"], hold_time=0.01)
        self.driver.press_sequence(["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"], inter_delay=0.01)


if __name__ == "__main__":
    unittest.main()
