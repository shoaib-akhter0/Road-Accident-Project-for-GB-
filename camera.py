import cv2
import numpy as np
import threading
import subprocess
import tkinter as tk
from camera_worker import CameraWorker
from PIL import Image, ImageTk

# ============================================================
# GLOBAL VARIABLES
# ============================================================
font = cv2.FONT_HERSHEY_SIMPLEX

# ------------------------------------------------------------
# DETECTION + PLAYBACK
# ------------------------------------------------------------
# All detection (PATH A / PATH C) and native-speed playback live in
# CameraWorker (camera_worker.py) - the same engine the web frontend
# uses. This desktop app is a thin OpenCV window over that worker, so
# both apps play the video at its own speed and detect exactly once
# per playthrough, at the collision moment.

# ============================================================
# BEEP FUNCTION FOR KALI LINUX
# ============================================================
def Beep(frequency=2500, duration=2000):
    try:
        subprocess.run(
            ["beep", "-f", str(frequency), "-l", str(duration)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        print(f"Beep error: {e}")

# ============================================================
# SHOW ACCIDENT ALERT WINDOW
# ============================================================
def show_alert_message():
    try:
        Beep(frequency=2500, duration=2000)

        alert_window = tk.Tk()
        alert_window.title("Accident Detection Alert")
        alert_window.geometry("500x300")
        alert_window.resizable(False, False)

        alert_label = tk.Label(
            alert_window,
            text="🚨 ACCIDENT DETECTED!\n\nIs the accident critical?",
            fg="red",
            font=("Helvetica", 18, "bold")
        )
        alert_label.pack(pady=30)

        gif_path = ""
        if gif_path:
            try:
                gif = Image.open(gif_path)
                resized_gif = gif.resize((150, 100), Image.Resampling.BICUBIC)
                global gif_image
                gif_image = ImageTk.PhotoImage(resized_gif)
                gif_label = tk.Label(alert_window, image=gif_image)
                gif_label.pack()
            except Exception as e:
                print(f"Error loading GIF: {e}")

        cancel_button = tk.Button(
            alert_window, text="Cancel", command=alert_window.destroy,
            font=("Helvetica", 11), padx=30, pady=5
        )
        cancel_button.pack(pady=5)

        alert_window.mainloop()

    except Exception as e:
        print(f"Alert window error: {e}")

# ============================================================
# START ALERT THREAD
# ============================================================
def start_alert_thread():
    alert_thread = threading.Thread(target=show_alert_message, daemon=True)
    alert_thread.start()

# ============================================================
# START APPLICATION
# ============================================================
def startapplication():
    worker = CameraWorker()
    worker.start()

    print("=" * 60)
    print("ROAD ACCIDENT DETECTION SYSTEM")
    print("=" * 60)
    print("Native-speed playback | one detection per playthrough.")
    print("Press Q to quit.")

    last_alert_time = None

    while True:
        jpeg = worker.get_jpeg()
        if jpeg is not None:
            frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8),
                                 cv2.IMREAD_COLOR)
            if frame is not None:
                snap = worker.get_snapshot()
                if (snap["status"] == "alert"
                        and snap["last_alert_time"] != last_alert_time):
                    last_alert_time = snap["last_alert_time"]
                    print("\n🚨 ACCIDENT DETECTED!")
                    print(f"CNN Confidence: {snap['accident_percent']:.2f}%  |  "
                          f"detected at: {last_alert_time}")
                    Beep(frequency=2500, duration=2000)
                    start_alert_thread()

                cv2.imshow("Road Accident Detection", frame)

        if cv2.waitKey(33) & 0xFF == ord("q"):
            break

    cv2.destroyAllWindows()
    print("\nApplication stopped.")

# ============================================================
# RUN APPLICATION
# ============================================================
if __name__ == "__main__":
    startapplication()