from flask import Flask, Response, jsonify, request, send_from_directory
from email.message import EmailMessage
from email.utils import parseaddr
import html
import os
import smtplib
import time

from dotenv import load_dotenv

from camera_worker import BASE_DIR, CameraWorker, PHOTOS_DIR

load_dotenv()
load_dotenv(os.path.join(BASE_DIR, ".env"))

app = Flask(__name__, static_folder="static", static_url_path="")

# CAM 01 - the accident-detection camera (full CNN + motion engine)
worker = CameraWorker()

# CAM 03 display-only clip.
NONACC_VIDEO = os.path.join(BASE_DIR, "videos", "nonaccc.mp4")
CAM3_VIDEO = os.path.join(BASE_DIR, "videos", "cam3.mp4")

# CAM 02 / CAM 03 - display-only cameras (no CNN, no motion engine):
# they just stream their clip at normal speed. CAM 04 is intentionally
# offline, so it has no worker at all.
extra_cameras = {
    "2": CameraWorker(video_path=NONACC_VIDEO, detect=False, playback_speed=1.0),
    "3": CameraWorker(video_path=CAM3_VIDEO, detect=False, playback_speed=1.0),
}

worker.start()
for cam in extra_cameras.values():
    cam.start()


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


def _mjpeg_generator(cam):
    while True:
        frame = cam.get_jpeg()
        if frame is not None:
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
        time.sleep(0.03)


@app.route("/video_feed")
def video_feed():
    return Response(_mjpeg_generator(worker),
                     mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/video_feed/<cam_id>")
def video_feed_cam(cam_id):
    cam = extra_cameras.get(cam_id)
    if cam is None:
        return "Camera offline", 404
    return Response(_mjpeg_generator(cam),
                     mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/status")
def status():
    return jsonify(worker.get_snapshot())


@app.route("/accident_photos/<path:filename>")
def accident_photo(filename):
    return send_from_directory(PHOTOS_DIR, filename)


def _valid_email_address(value):
    address = parseaddr(str(value or ""))[1]
    return bool(address and address == str(value).strip() and "@" in address)


def send_email_alert(message, detection_time, capture_url, confidence=None):
    sender = os.getenv("EMAIL_SENDER", "").strip()
    password = os.getenv("EMAIL_PASSWORD", "")
    recipient = os.getenv("EMERGENCY_EMAIL", "").strip()
    smtp_server = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com").strip()
    try:
        smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
    except ValueError:
        return False, "SMTP port is invalid."

    if not sender or not password:
        return False, "Email sender credentials are not configured."
    if not recipient:
        return False, "Emergency email recipient is not configured."
    if not _valid_email_address(sender) or not _valid_email_address(recipient):
        return False, "Email sender or recipient address is invalid."

    safe_time = str(detection_time or "Unknown")
    safe_capture_url = str(capture_url or "Not available")
    if safe_capture_url.startswith("/"):
        safe_capture_url = request.host_url.rstrip("/") + safe_capture_url
    safe_message = str(message).strip()
    confidence_line = f"\nConfidence: {confidence}%" if confidence is not None else ""
    text_body = (
        "ACCIDENT DETECTED\n\n"
        f"Detection Time: {safe_time}\n\n"
        "Message:\n"
        "An accident has been detected by the Road Accident Detection System.\n\n"
        f"Accident Capture: {safe_capture_url}{confidence_line}\n\n"
        f"{safe_message}\n\n"
        "Please check the accident immediately."
    )
    escaped_url = html.escape(safe_capture_url, quote=True)
    html_body = (
        "<h2>ACCIDENT DETECTED</h2>"
        f"<p><strong>Detection Time:</strong> {html.escape(safe_time)}</p>"
        "<p>An accident has been detected by the Road Accident Detection System.</p>"
        f'<p><strong>Accident Capture:</strong> <a href="{escaped_url}">View capture</a></p>'
        f"<p>{html.escape(safe_message)}</p>"
        "<p>Please check the accident immediately.</p>"
    )

    email = EmailMessage()
    email["Subject"] = "🚨 ACCIDENT ALERT - Road Accident Detection System"
    email["From"] = sender
    email["To"] = recipient
    email.set_content(text_body)
    email.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(sender, password)
            smtp.send_message(email)
        return True, "Alert email sent successfully"
    except smtplib.SMTPAuthenticationError:
        app.logger.error("Gmail authentication failed while sending alert")
        return False, "Gmail authentication failed. Check the App Password."
    except smtplib.SMTPRecipientsRefused:
        app.logger.error("Gmail refused the emergency email recipient")
        return False, "Emergency email recipient was rejected."
    except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, OSError):
        app.logger.error("Unable to connect to Gmail SMTP while sending alert")
        return False, "Could not connect to Gmail SMTP."
    except smtplib.SMTPException:
        app.logger.error("Gmail SMTP failed while sending alert")
        return False, "Gmail SMTP failed to send the alert."
    except Exception:
        app.logger.error("Unexpected error while sending alert email")
        return False, "Unexpected error while sending alert email."


@app.route("/api/send-alert", methods=["POST"])
def api_send_alert():
    payload = request.get_json(silent=True) or {}
    message = payload.get("message")

    if not isinstance(message, str) or not message.strip():
        return jsonify({"success": False, "message": "Emergency alert message is required."}), 400

    ok, message_text = send_email_alert(
        message,
        payload.get("detection_time"),
        payload.get("capture_url"),
        payload.get("confidence"),
    )
    return jsonify({"success": ok, "message": message_text})


@app.route("/pause", methods=["POST"])
def pause():
    # Freeze the video wall on the server side; the detection engine
    # keeps running (armed) in the background.
    worker.pause_feed()
    for cam in extra_cameras.values():
        cam.pause_feed()
    return jsonify({"success": True, "paused": True})


@app.route("/play", methods=["POST"])
def play():
    # Continue playback from the frame where it was paused.
    worker.resume_feed()
    for cam in extra_cameras.values():
        cam.resume_feed()
    return jsonify({"success": True, "paused": False})


@app.route("/resume", methods=["POST"])
def resume():
    # Acknowledge-only: dismissing the alert does NOT re-arm the alarm.
    # The worker re-arms itself when the video restarts, giving exactly
    # one detection per playthrough.
    return jsonify({"success": True})


if __name__ == "__main__":
    app.run(host=os.getenv("FLASK_HOST", "0.0.0.0"),
            port=int(os.getenv("FLASK_PORT", "5000")),
            debug=False)