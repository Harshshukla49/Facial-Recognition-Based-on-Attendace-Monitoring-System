"""
Launcher script for Face Recognition Based Attendance Monitoring System on Localhost.
"""
import os
import sys
import webbrowser
import threading
import time

def main():
    print("=" * 65)
    print("  FACE RECOGNITION BASED ATTENDANCE MONITORING SYSTEM")
    print("  Running on Localhost: http://127.0.0.1:5000")
    print("=" * 65)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    haar_path = os.path.join(base_dir, "haarcascade_frontalface_default.xml")
    
    if not os.path.isfile(haar_path):
        print("[-] Warning: haarcascade_frontalface_default.xml not found!")
    else:
        print("[+] Haar cascade detector verified.")

    # Auto-open browser after 1.5 seconds
    def open_browser():
        time.sleep(1.5)
        print("[+] Opening web dashboard in default browser...")
        try:
            webbrowser.open("http://127.0.0.1:5000")
        except Exception as e:
            print(f"[-] Could not auto-open browser: {e}")

    threading.Thread(target=open_browser, daemon=True).start()

    from app import app
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

if __name__ == "__main__":
    main()
