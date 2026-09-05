import numpy as np
import os
import tensorflow as tf
import cv2
from collections import deque

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_MODEL = os.path.join(_BASE_DIR, "models",
                              "mobilenetv2_accident_detection.keras")


class AccidentDetectionModel(object):
    """
    Wraps the trained MobileNetV2 accident-detection model.

    Verified from the saved .keras file:
      - Input: 224x224x3, RAW pixel values in [0, 255] (model has a
        Rescaling(1/127.5, offset=-1) layer built in — do NOT pre-normalize).
      - Output: Dense(1, sigmoid).
      - Class indices: {'Accident': 0, 'NonAccident': 1}, so:
            P(Accident) = 1 - sigmoid_output
    """

    def __init__(self, model_path=_DEFAULT_MODEL):
        self.model = tf.keras.models.load_model(model_path)

    def predict_accident(self, frame_rgb_224):
        roi = frame_rgb_224.astype(np.float32)
        roi = np.expand_dims(roi, axis=0)

        raw_sigmoid = float(self.model.predict(roi, verbose=0)[0][0])
        accident_probability = 1.0 - raw_sigmoid

        label = "Accident" if accident_probability >= 0.5 else "No Accident"
        return label, accident_probability


class MotionSpikeDetector(object):
    """
    Frame-differencing motion detector. A real crash has a sudden motion
    spike (sudden stop / impact) relative to the recent baseline; ordinary
    traffic does not. Self-calibrates per video/stream using a running
    mean + standard deviation of motion, flagging a spike only when the
    current frame is a statistical outlier (z-score) relative to that
    video's own recent motion distribution.
    """

    def __init__(self, fps=25.0, baseline_seconds=3.0, warmup_seconds=2.0, z_thresh=3.5):
        baseline_window = max(10, round(fps * baseline_seconds))
        self.warmup_frames = max(5, round(fps * warmup_seconds))
        self.z_thresh = z_thresh
        self.history = deque(maxlen=baseline_window)
        self.prev_gray = None
        self.last_frac = 0.0

    def update(self, frame_bgr):
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        if self.prev_gray is None:
            self.prev_gray = gray
            self.history.append(0.0)
            return False

        diff = cv2.absdiff(gray, self.prev_gray)
        motion_score = float(np.mean(diff))
        self.last_frac = float(np.mean(diff > 25)) * 100.0
        self.prev_gray = gray

        is_spike = False
        if len(self.history) >= self.warmup_frames:
            mean = float(np.mean(self.history))
            std = float(np.std(self.history))
            is_spike = std > 1e-6 and (motion_score - mean) > self.z_thresh * std

        self.history.append(motion_score)
        return is_spike