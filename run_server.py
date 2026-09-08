"""
Production Server Runner for VisionAttend AI Enterprise Platform.
"""
import os
import sys
import webbrowser
import threading
import time

def main():
    print("=" * 75)
    print("  VISIONATTEND AI - PRODUCTION FACIAL RECOGNITION PLATFORM")
    print("  Operating on Localhost: http://127.0.0.1:5000")
    print("=" * 75)

    from config import Config
    Config.initialize_directories()

    from core.database import Database
    Database.init_schema()

    # Auto open browser after 1.5 seconds
    def launch_browser():
        time.sleep(1.5)
        print("[+] Opening Enterprise Dashboard in default browser: http://127.0.0.1:5000")
        try:
            webbrowser.open("http://127.0.0.1:5000")
        except Exception as e:
            print(f"[-] Could not auto-launch browser: {e}")

    threading.Thread(target=launch_browser, daemon=True).start()

    from app import app
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

if __name__ == "__main__":
    main()
