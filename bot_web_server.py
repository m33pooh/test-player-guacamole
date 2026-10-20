import os
import time
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import cv2
import numpy as np

PORT = 18888
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


class TelemetryHub:
    """
    Thread-safe Central Telemetry and Frame Buffer for the Bot Web Dashboard.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(TelemetryHub, cls).__new__(cls)
                cls._instance._init_hub()
            return cls._instance

    def _init_hub(self):
        self.lock = threading.Lock()
        self.latest_raw_frame = None
        self.latest_annotated_frame = None
        self.latest_jpeg = None
        self.current_state = "IDLE"
        self.hp_ratio = 1.0
        self.in_town = True
        self.detected_monsters = []
        self.current_target = None
        self.current_action = "Waiting for bot to start..."
        self.action_history = []
        self.scan_history = []
        self.stats = {
            "uptime_seconds": 0,
            "monsters_engaged": 0,
            "deaths_recovered": 0,
            "town_refills": 0,
            "warps_executed": 0,
            "total_frames_processed": 0,
            "start_time": time.time()
        }

    def update_frame(self, raw_frame, annotated_frame):
        with self.lock:
            self.latest_raw_frame = raw_frame
            self.latest_annotated_frame = annotated_frame
            if annotated_frame is not None:
                success, encoded = cv2.imencode(".jpg", annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
                if success:
                    self.latest_jpeg = encoded.tobytes()
            self.stats["total_frames_processed"] += 1
            self.stats["uptime_seconds"] = int(time.time() - self.stats["start_time"])

    def record_action(self, action_type, description, details=None):
        with self.lock:
            self.current_action = description
            entry = {
                "id": len(self.action_history) + 1,
                "timestamp": time.strftime("%H:%M:%S"),
                "state": self.current_state,
                "type": action_type,
                "description": description,
                "details": details or {}
            }
            self.action_history.insert(0, entry)
            if len(self.action_history) > 60:
                self.action_history.pop()

            # Record stats
            if "Engaging monster" in description:
                self.stats["monsters_engaged"] += 1
            elif "Respawn In Town" in description or "Respawned" in description:
                self.stats["deaths_recovered"] += 1
            elif "Refilling HP" in description:
                self.stats["town_refills"] += 1
            elif "Warping" in description or "Map crossed" in description:
                self.stats["warps_executed"] += 1

    def record_scan_snapshot(self, frame_thumb_b64, state, detections, action):
        with self.lock:
            snapshot = {
                "id": len(self.scan_history) + 1,
                "timestamp": time.strftime("%H:%M:%S"),
                "state": state,
                "detections": detections,
                "action": action,
                "thumb_b64": frame_thumb_b64
            }
            self.scan_history.insert(0, snapshot)
            if len(self.scan_history) > 30:
                self.scan_history.pop()

    def update_telemetry(self, state, hp_ratio, in_town, monsters, target_info):
        with self.lock:
            self.current_state = state
            self.hp_ratio = round(hp_ratio, 3)
            self.in_town = in_town
            self.detected_monsters = monsters
            self.current_target = target_info

    def get_telemetry_json(self):
        with self.lock:
            return {
                "state": self.current_state,
                "hp_ratio": self.hp_ratio,
                "hp_percent": int(self.hp_ratio * 100),
                "in_town": self.in_town,
                "monsters_count": len(self.detected_monsters),
                "monsters": self.detected_monsters[:10],
                "current_target": self.current_target,
                "current_action": self.current_action,
                "stats": self.stats,
                "timestamp": time.strftime("%H:%M:%S")
            }

    def get_latest_jpeg(self):
        with self.lock:
            return self.latest_jpeg

    def get_actions(self):
        with self.lock:
            return list(self.action_history)

    def get_scan_history(self):
        with self.lock:
            return list(self.scan_history)


class BotDashboardRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress standard logging to keep terminal clean
        return

    def do_GET(self):
        hub = TelemetryHub()
        clean_path = self.path.split("?")[0]

        if clean_path == "/" or clean_path == "/index.html":
            self.serve_file(os.path.join(STATIC_DIR, "index.html"), "text/html; charset=utf-8")
        elif clean_path.startswith("/static/"):
            rel_path = clean_path[8:]
            file_path = os.path.join(STATIC_DIR, rel_path)
            content_type = "text/plain"
            if file_path.endswith(".css"):
                content_type = "text/css; charset=utf-8"
            elif file_path.endswith(".js"):
                content_type = "application/javascript; charset=utf-8"
            elif file_path.endswith(".png"):
                content_type = "image/png"
            elif file_path.endswith(".jpg"):
                content_type = "image/jpeg"
            self.serve_file(file_path, content_type)
        elif clean_path == "/api/telemetry":
            data = hub.get_telemetry_json()
            self.send_json(data)
        elif clean_path == "/api/actions":
            data = hub.get_actions()
            self.send_json(data)
        elif clean_path == "/api/history":
            data = hub.get_scan_history()
            self.send_json(data)
        elif clean_path == "/api/latest_frame.jpg":
            jpeg = hub.get_latest_jpeg()
            if jpeg:
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(jpeg)))
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(jpeg)
            else:
                self.send_response(404)
                self.end_headers()
        elif clean_path == "/api/stream":
            self.stream_mjpeg()
        else:
            self.send_response(404)
            self.end_headers()

    def serve_file(self, file_path, content_type):
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_response(404)
            self.end_headers()

    def send_json(self, data):
        content = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def stream_mjpeg(self):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        try:
            while True:
                jpeg = self.hub.get_latest_jpeg()
                if jpeg is not None:
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode("utf-8"))
                    self.wfile.write(jpeg)
                    self.wfile.write(b"\r\n")
                time.sleep(0.08)
        except Exception:
            pass


def start_dashboard_server(port=PORT):
    server = HTTPServer(("0.0.0.0", port), BotDashboardRequestHandler)
    print(f"=== Bot Visual Telemetry Web Server started at http://localhost:{port} ===", flush=True)
    server.serve_forever()


def start_dashboard_in_background(port=PORT):
    thread = threading.Thread(target=start_dashboard_server, args=(port,), daemon=True)
    thread.start()
    return thread


if __name__ == "__main__":
    start_dashboard_server(PORT)
