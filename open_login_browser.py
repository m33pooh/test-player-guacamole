import os
import subprocess
import sys
import time

GUACAMOLE_URL = "http://localhost:60289/guacamole/"
PROFILE_DIR = os.path.expanduser(r"~\.chrome_game_profile")


def open_standalone_browser():
    print("=" * 60)
    print(" === Launching Dedicated Persistent Game Browser (CDP 9222) ===")
    print("=" * 60)

    # 1. Locate Chrome / Chromium binary
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    chrome_path = None
    for c in candidates:
        if os.path.exists(c):
            chrome_path = c
            break

    if not chrome_path:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                chrome_path = p.chromium.executable_path
        except Exception:
            pass

    if not chrome_path:
        print("[Error] No Chrome or Chromium executable found.")
        return

    os.makedirs(PROFILE_DIR, exist_ok=True)

    print(f"[Browser Path] {chrome_path}")
    print(f"[Profile Dir]  {PROFILE_DIR}")
    print(f"[Target URL]   {GUACAMOLE_URL}")
    print("[Port]         9222 (Chrome DevTools Protocol)")

    # 2. Launch as an isolated, persistent Windows detached process with dedicated user-data-dir
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200

    cmd = [
        chrome_path,
        "--remote-debugging-port=9222",
        "--remote-debugging-address=127.0.0.1",
        "--remote-allow-origins=*",
        f"--user-data-dir={PROFILE_DIR}",
        "--start-maximized",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        GUACAMOLE_URL,
    ]

    try:
        subprocess.Popen(
            cmd,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
        print("\n[Success] Dedicated Game Browser launched successfully!")
        print("[Info] This browser instance is completely isolated and will NEVER close on its own.")
    except Exception as e:
        print(f"[Error launching browser] {e}")


if __name__ == "__main__":
    open_standalone_browser()
