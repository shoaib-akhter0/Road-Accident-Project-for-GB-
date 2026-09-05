import cv2
import numpy as np
import os
import threading
import time
from collections import deque

from dotenv import load_dotenv

from detection import AccidentDetectionModel, MotionSpikeDetector

# project root - all asset paths are anchored here so the app works no
# matter which directory it is launched from
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# load secrets/overrides from .env (email credentials and local path overrides)
load_dotenv(os.path.join(BASE_DIR, ".env"))

# ============================================================
# CONFIG - tuned for the MobileNetV2 model + this footage (A.avi)
# ============================================================
# Measured frame-by-frame on A.avi with mobilenetv2_accident_detection.keras:
#   - collision window t=3.1-4.5s: changed-pixel fraction 1.8-4.1%,
#     z-score motion spikes at t=3.2-3.4s, CNN only 2-8% (this model
#     does not recognize the impact frames themselves)
#   - calm scenes: changed-pixel fraction < 0.75%, CNN 0-2%
#   - aftermath t=11.7-14.3s: CNN 27-54%, no motion burst
#
# Trigger = IMPACT PATH or CNN PATH (OR):
#   IMPACT PATH - sustained changed-pixel burst (>= 2.0% of pixels in
#     many frames within the last 0.6s) plus at least one z-score motion
#     spike in the last 1.5s. On this clip it fires at ~t=3.3s, exactly
#     when the car hits the bike and it starts falling. Calm scenes
#     never come close (max 0.75%).
#   CNN PATH - sustained high CNN confidence (safety net for footage
#     where the model does recognize the accident visually).
IMPACT_FRAC_THRESHOLD = 2.0       # % of pixels with |diff| > 25
IMPACT_FRAC_WINDOW_SECONDS = 0.6  # look at bursts within this window
IMPACT_MIN_BURST_FRAMES = 8       # frames above threshold inside window
IMPACT_SPIKE_LOOKBACK_SECONDS = 1.5
IMPACT_MIN_SPIKES = 1

# The impact burst starts the moment the car clips the bike (~t=3.3s),
# but the alert should show the OUTCOME - bike flat on the road, rider
# down (~t=5.5s). So once a trigger condition is met, hold it for this
# long before latching the alarm; the snapshot then captures the fallen
# bike instead of mid-fall blur. Raise/lower to shift the alert moment.
# NOTE: measured in VIDEO seconds - independent of PLAYBACK_SPEED.
ALERT_CONFIRM_DELAY_SECONDS = 2.0

CNN_THRESHOLD = 60.0              # sustained CNN % needed (CNN path)
CNN_WINDOW_SECONDS = 0.5
CNN_MIN_FRAC = 0.7                # fraction of samples above threshold

MOTION_BASELINE_SECONDS = 3.0
MOTION_WARMUP_SECONDS = 1.5
MOTION_Z_THRESH = 3.0

VIDEO_PATH = os.getenv("VIDEO_PATH", os.path.join(BASE_DIR, "videos", "A.avi"))
MODEL_PATH = os.getenv("MODEL_PATH",
                       os.path.join(BASE_DIR, "models",
                                    "mobilenetv2_accident_detection.keras"))
PHOTOS_DIR = os.getenv("PHOTOS_DIR", os.path.join(BASE_DIR, "accident_photos"))

# Playback speed as a TRUE speed multiplier:
#   1.0 = the file's raw fps, 0.5 = half speed (slower), 2.0 = double.
# This CCTV clip's header claims 30fps but the footage looks ~2x fast
# when played at that rate, so 0.5 gives natural-looking motion.
PLAYBACK_SPEED = 0.5

font = cv2.FONT_HERSHEY_SIMPLEX


def save_accident_photo(frame):
    try:
        if not os.path.exists(PHOTOS_DIR):
            os.makedirs(PHOTOS_DIR)
        filename = time.strftime("%Y-%m-%d-%H%M%S") + ".jpg"
        path = os.path.join(PHOTOS_DIR, filename)
        cv2.imwrite(path, frame)
        return filename
    except Exception as e:
        print(f"Error saving accident photo: {e}")
        return None


class CameraWorker:
    """
    Two independent loops:

    1) DISPLAY loop - reads every frame at the video's real fps, paced so
       playback runs at normal speed (never fast-forwards), and runs the
       cheap motion check on every frame so brief impact bursts are never
       missed. Supports server-side pause: the frame freezes while
       detection state stays armed.

    2) INFERENCE loop - runs the CNN as fast as the hardware allows on
       the latest frame only, so the expensive model never slows down
       playback.

    Exactly ONE alert per playthrough: the alarm latches when triggered
    and re-arms only when the video restarts from the beginning.
    """

    def __init__(self, video_path=None, detect=True, playback_speed=None):
        # per-camera configuration (defaults preserve the original
        # single-camera behavior: A.avi + full detection engine)
        self.video_path = video_path or VIDEO_PATH
        self.detect = detect
        self.playback_speed = (playback_speed if playback_speed is not None
                               else PLAYBACK_SPEED)

        self.lock = threading.Lock()
        self.latest_jpeg = None
        self.accident_percent = 0.0
        self.spike_count = 0
        self.alarm_triggered = False
        self.last_alert_time = None
        self.last_alert_photo = None

        self.frame_lock = threading.Lock()
        self.current_frame = None
        self.video_fps = 25.0

        # pause state: True = video/screen frozen, detection stays armed
        self.pause_lock = threading.Lock()
        self.paused = False

        self.spike_lock = threading.Lock()
        self.spike_events = deque()  # (timestamp, bool z-spike)
        self.frac_events = deque()   # (timestamp, changed-pixel %)

        # bumped at the start of every playthrough so the inference loop
        # can drop stale pending-trigger state from the previous play
        self.play_id = 0

        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        if self.detect:
            # load + warm up the model BEFORE playback so the CNN is live
            # at video t=0 (the first predict traces the TF graph and is
            # slow). Display-only cameras skip the model entirely.
            self.model = AccidentDetectionModel(MODEL_PATH)
            self.model.predict_accident(np.zeros((224, 224, 3), dtype=np.float32))
        threading.Thread(target=self._display_loop, daemon=True).start()
        if self.detect:
            threading.Thread(target=self._inference_loop, daemon=True).start()

    def rearm(self):
        """Video restarted: allow exactly one detection for the new play."""
        with self.lock:
            self.alarm_triggered = False
        with self.spike_lock:
            self.spike_events.clear()
            self.frac_events.clear()

    def pause_feed(self):
        """Freeze the video/screen. Detection stays armed and running."""
        with self.pause_lock:
            self.paused = True

    def resume_feed(self):
        """Continue playback from the frame where it was paused."""
        with self.pause_lock:
            self.paused = False

    def get_snapshot(self):
        with self.lock:
            status = "alert" if self.alarm_triggered else "monitoring"
            return {
                "status": status,
                "accident_percent": round(self.accident_percent, 2),
                "spike_count": self.spike_count,
                "alarm_triggered": self.alarm_triggered,
                "last_alert_time": self.last_alert_time,
                "last_alert_photo": self.last_alert_photo,
            }

    def get_jpeg(self):
        with self.lock:
            return self.latest_jpeg

    # ----------------------------------------------------------------
    # LOOP 1: normal-speed playback + motion detection (full fps)
    # ----------------------------------------------------------------
    def _display_loop(self):
        while True:
            video = cv2.VideoCapture(self.video_path)
            if not video.isOpened():
                print(f"ERROR: could not open {self.video_path}")
                time.sleep(1.0)
                continue

            fps = video.get(cv2.CAP_PROP_FPS) or 25.0
            with self.lock:
                self.video_fps = fps
                self.play_id += 1
            # fresh detector per playthrough so warmup/baseline belong
            # to this play, not the previous one
            motion_detector = MotionSpikeDetector(
                fps=fps,
                baseline_seconds=MOTION_BASELINE_SECONDS,
                warmup_seconds=MOTION_WARMUP_SECONDS,
                z_thresh=MOTION_Z_THRESH,
            )

            # speed multiplier: period grows as speed drops, so 0.5
            # really means half speed (the old formula was inverted -
            # lower values made playback FASTER, which is why the video
            # kept looking too fast no matter what was configured)
            frame_period = 1.0 / (fps * self.playback_speed)
            start_wall = time.time()
            frame_idx = 0

            while True:
                try:
                    with self.pause_lock:
                        paused = self.paused
                    if paused:
                        # screen frozen: hold this frame; keep anchoring
                        # the timeline so playback resumes from HERE
                        # without any jump or fast-forward
                        start_wall = time.time() - frame_idx * frame_period
                        time.sleep(0.1)
                        continue

                    target_time = start_wall + frame_idx * frame_period
                    now = time.time()
                    if now < target_time:
                        time.sleep(target_time - now)
                    elif now - target_time > 0.25:
                        # fell behind (CPU contention etc.) - NEVER fast-
                        # forward to catch up; shift the timeline instead
                        start_wall += now - target_time

                    ret, frame = video.read()
                    if not ret:
                        break  # end of video -> loop it

                    with self.frame_lock:
                        self.current_frame = frame

                    # motion metrics at FULL native fps (detection
                    # cameras only - display-only cameras just stream)
                    if self.detect:
                        is_spike = motion_detector.update(frame)
                        frac = motion_detector.last_frac
                        ts = time.time()
                        with self.spike_lock:
                            self.spike_events.append((ts, is_spike))
                            self.frac_events.append((ts, frac))
                            while (self.spike_events and
                                   ts - self.spike_events[0][0] > IMPACT_SPIKE_LOOKBACK_SECONDS):
                                self.spike_events.popleft()
                            while (self.frac_events and
                                   ts - self.frac_events[0][0] > IMPACT_FRAC_WINDOW_SECONDS):
                                self.frac_events.popleft()

                    with self.lock:
                        show_alert_banner = self.alarm_triggered
                        pct = self.accident_percent

                    display_frame = frame
                    if show_alert_banner:
                        display_frame = frame.copy()
                        cv2.rectangle(display_frame, (0, 0), (420, 50), (0, 0, 0), -1)
                        cv2.putText(display_frame, f"ACCIDENT: {pct:.2f}%",
                                    (15, 35), font, 0.9, (0, 0, 255), 2)

                    # stream jpeg at reduced size to stay inside the
                    # per-frame time budget (saved photos use full res)
                    if display_frame.shape[1] > 1280:
                        s = 1280.0 / display_frame.shape[1]
                        display_frame = cv2.resize(
                            display_frame, (1280, int(display_frame.shape[0] * s)))
                    ok, buf = cv2.imencode(
                        ".jpg", display_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                    if ok:
                        with self.lock:
                            self.latest_jpeg = buf.tobytes()

                    frame_idx += 1
                except Exception as e:
                    import traceback
                    print("DISPLAY LOOP ERROR:", e)
                    traceback.print_exc()
                    break

            video.release()
            # one full playthrough done: re-arm for the next replay
            self.rearm()

    # ----------------------------------------------------------------
    # LOOP 2: CNN inference + combined trigger check
    # ----------------------------------------------------------------
    def _inference_loop(self):
        model = self.model

        # wait for the display loop to publish a first frame
        while True:
            with self.frame_lock:
                have_frame = self.current_frame is not None
            if have_frame:
                break
            time.sleep(0.05)

        cnn_events = deque()  # (timestamp, bool: cnn >= CNN_THRESHOLD)
        pending_since = None  # trigger condition met, waiting out the confirm delay
        last_play_id = None

        while True:
            try:
                with self.frame_lock:
                    frame = self.current_frame

                if frame is None:
                    time.sleep(0.02)
                    continue

                # new playthrough: drop any stale pending trigger
                with self.lock:
                    play_id = self.play_id
                if play_id != last_play_id:
                    last_play_id = play_id
                    pending_since = None
                    cnn_events.clear()

                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                roi = cv2.resize(rgb_frame, (224, 224))
                _, accident_probability = model.predict_accident(roi)
                accident_percent = accident_probability * 100.0

                now = time.time()

                # CNN PATH: sustained high confidence
                cnn_events.append((now, accident_percent >= CNN_THRESHOLD))
                while cnn_events and now - cnn_events[0][0] > CNN_WINDOW_SECONDS:
                    cnn_events.popleft()
                cnn_full = (cnn_events and
                            (now - cnn_events[0][0]) >= CNN_WINDOW_SECONDS * 0.8)
                cnn_frac = (sum(1 for _, v in cnn_events if v) / len(cnn_events)
                            if cnn_events else 0.0)
                cnn_path = cnn_full and cnn_frac >= CNN_MIN_FRAC

                # IMPACT PATH: sustained changed-pixel burst + z-spike
                with self.spike_lock:
                    while (self.spike_events and
                           now - self.spike_events[0][0] > IMPACT_SPIKE_LOOKBACK_SECONDS):
                        self.spike_events.popleft()
                    spike_count = sum(1 for _, v in self.spike_events if v)
                    while (self.frac_events and
                           now - self.frac_events[0][0] > IMPACT_FRAC_WINDOW_SECONDS):
                        self.frac_events.popleft()
                    burst_frames = sum(
                        1 for _, f in self.frac_events if f >= IMPACT_FRAC_THRESHOLD)
                impact_path = (burst_frames >= IMPACT_MIN_BURST_FRAMES
                               and spike_count >= IMPACT_MIN_SPIKES)

                real_accident_signal = cnn_path or impact_path

                with self.lock:
                    self.accident_percent = accident_percent
                    self.spike_count = spike_count
                    already_triggered = self.alarm_triggered

                if not already_triggered:
                    if real_accident_signal and pending_since is None:
                        # condition met at the IMPACT - start the confirm
                        # timer so the alarm lands on the outcome (bike
                        # down on the road), not the first contact
                        pending_since = now
                    # delay is in VIDEO seconds: scale to wall time so the
                    # snapshot lands on the same video frame at any speed
                    if (pending_since is not None
                            and now - pending_since >=
                            ALERT_CONFIRM_DELAY_SECONDS / self.playback_speed):
                        pending_since = None
                        snapshot_frame = frame.copy()
                        cv2.rectangle(snapshot_frame, (0, 0), (420, 50), (0, 0, 0), -1)
                        cv2.putText(snapshot_frame, "ACCIDENT DETECTED",
                                    (15, 35), font, 0.9, (0, 0, 255), 2)
                        photo_name = save_accident_photo(snapshot_frame)

                        with self.lock:
                            self.alarm_triggered = True
                            self.last_alert_time = time.strftime("%Y-%m-%d %H:%M:%S")
                            self.last_alert_photo = photo_name

                # no artificial sleep: the model's own cost paces this loop
            except Exception as e:
                import traceback
                print("INFERENCE LOOP ERROR:", e)
                traceback.print_exc()
                time.sleep(0.5)
