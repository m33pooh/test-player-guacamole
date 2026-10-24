import unittest
from maple.app.capture.dxgi_capture import DXGICapture
from maple.app.capture.guacamole_capture import GuacamoleCapture


class TestCaptureEngines(unittest.TestCase):

    def test_dxgi_capture_init(self):
        cap = DXGICapture(target_fps=30)
        self.assertEqual(cap.target_fps, 30)
        self.assertIn("parsec", cap.window_keywords)
        self.assertIn("maplestory", cap.window_keywords)
        self.assertFalse(cap.is_connected)

    def test_dxgi_keyword_priority(self):
        cap = DXGICapture()
        # Verify priority ordering
        keywords = cap.window_keywords
        self.assertLess(keywords.index("parsec"), keywords.index("chrome"))
        self.assertLess(keywords.index("parsec"), keywords.index("edge"))

    def test_guacamole_capture_init(self):
        guac = GuacamoleCapture(cdp_endpoint="http://localhost:9222")
        self.assertEqual(guac.cdp_endpoint, "http://localhost:9222")
        self.assertIsNone(guac.page)
        w, h = guac.get_viewport_size()
        self.assertGreater(w, 0)
        self.assertGreater(h, 0)


if __name__ == "__main__":
    unittest.main()
