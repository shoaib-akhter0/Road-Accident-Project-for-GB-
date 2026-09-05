# Road Accident Detection & Alarming System for GB

A real-time road accident detection and alarming system built for CCTV
surveillance. A dual-signal engine (MobileNetV2 CNN + motion-spike
analysis) watches camera feeds, latches exactly one alert per incident,
saves an evidence photo, and can notify emergency contacts by Gmail email.
Ships with a professional multi-camera monitoring dashboard.

<video controls width="720" preload="metadata">
  <source src="media/project-demo.mp4" type="video/mp4">
  Your browser does not support embedded video. [Open the demo video](media/project-demo.mp4).
</video>

## Features

- **Dual-signal detection engine** — CNN confidence path + impact
  motion-burst path (changed-pixel fraction + z-score spikes), tuned to
  fire at the moment of the crash outcome
- **Multi-camera dashboard (2×2 grid)** — CAM 01 with live AI detection,
  two display-only channels, and an offline channel with a NO SIGNAL
  state
- **One alert per playthrough** — the alarm latches on detection and
  re-arms only when the video restarts
- **Server-side pause/resume** — the video wall freezes while the
  detection engine stays armed
- **Evidence capture** — annotated snapshot saved to `accident_photos/`
  at the moment of the alert
- **Email alerting** — one-click emergency notification via Gmail SMTP
- **Desktop mode** — lightweight OpenCV window app in addition to the
  web dashboard

## Project Structure

```
├── app.py                 # Flask web server (dashboard + camera APIs)
├── camera_worker.py       # Core engine: playback, motion, CNN, alert logic
├── detection.py           # Model wrapper + motion-spike detector
├── main.py                # Desktop app entry point
├── camera.py              # Desktop app camera window
├── static/                # Dashboard UI (HTML/CSS/JS)
├── models/                # Trained model (.keras)
├── videos/                # Camera footage used by the dashboard
├── media/                 # Project demonstration video
├── notebooks/             # Model training notebook
├── accident_photos/       # Saved alert snapshots (generated)
├── .env.example           # Environment template - copy to .env
├── .gitignore
└── requirements.txt
```

## Requirements

- **Python 3.13** (TensorFlow has no wheels for 3.14 yet)
- pip / [uv](https://github.com/astral-sh/uv)

## Setup

```bash
# 1. Create and activate the virtual environment (Python 3.13)
uv venv --python 3.13 --seed .venv     # or: python3.13 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# update .env with your Gmail App Password and recipient
```

## Configuration (.env)

| Variable | Purpose |
| --- | --- |
| `EMAIL_SENDER` | Gmail address used to send alerts |
| `EMAIL_PASSWORD` | Gmail App Password stored only in `.env` |
| `EMERGENCY_EMAIL` | Email address that receives alerts |
| `EMAIL_SMTP_SERVER` / `EMAIL_SMTP_PORT` | Gmail SMTP settings (default `smtp.gmail.com:587`) |
| `FLASK_HOST` / `FLASK_PORT` | Web server bind address (default `0.0.0.0:5000`) |
| `VIDEO_PATH` / `MODEL_PATH` / `PHOTOS_DIR` | Optional asset path overrides |

For Gmail, enable 2-Step Verification in the sender account, then create an
App Password under Google Account > Security > App passwords. Put that
16-character value in `EMAIL_PASSWORD`; do not use the regular Gmail password.

## Run

**Web dashboard** (recommended):

```bash
source .venv/bin/activate
python app.py
# open http://localhost:5000
```

Test email delivery independently:

```bash
python test_email.py
```

**Desktop window app:**

```bash
python main.py
```

## Dashboard Channels

| Channel | Source | Behavior |
| --- | --- | --- |
| CAM 01 · Intersection | `videos/A.avi` | Full AI detection, alert badge + modal |
| CAM 02 · Main Boulevard | `videos/nonaccc.mp4` | Display-only, no CNN cost |
| CAM 03 · City Gate | `videos/cam3.mp4` | Display-only, no CNN cost |
| CAM 04 · Bridge Road | — | Intentionally offline (NO SIGNAL) |

## Model

`models/mobilenetv2_accident_detection.keras` — MobileNetV2 binary
classifier (Accident / NonAccident), 224×224 raw RGB input with a
built-in rescaling layer. Training pipeline lives in
`notebooks/accident_classification.ipynb`.

## Demo

The repository includes a short walkthrough of the dashboard and detection
workflow. Use the player above, or [open the demo video directly](media/project-demo.mp4).

## License

Open source under the [MIT License](LICENSE).

## Owner

Shoaib Akhter
