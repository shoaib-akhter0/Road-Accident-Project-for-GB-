import os
import smtplib
from email.message import EmailMessage
from email.utils import parseaddr

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

sender = os.getenv("EMAIL_SENDER", "").strip()
password = os.getenv("EMAIL_PASSWORD", "")
recipient = os.getenv("EMERGENCY_EMAIL", "").strip()
smtp_server = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com").strip()

try:
    smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
except ValueError:
    raise SystemExit("SMTP port is invalid")

sender_address = parseaddr(sender)[1]
recipient_address = parseaddr(recipient)[1]
if not sender or not password or sender_address != sender or not recipient_address or recipient_address != recipient:
    raise SystemExit("Missing or invalid email configuration")

email = EmailMessage()
email["Subject"] = "Road Accident Detection System - SMTP Test"
email["From"] = sender
email["To"] = recipient
email.set_content("This is a test email from the Road Accident Detection System.")

print("Connecting to Gmail SMTP...")
try:
    with smtplib.SMTP(smtp_server, smtp_port, timeout=20) as smtp:
        smtp.starttls()
        smtp.login(sender, password)
        print("Sending test email...")
        smtp.send_message(email)
    print("✓ Email sent successfully")
except smtplib.SMTPAuthenticationError:
    print("✗ Email failed")
    print("Reason: Gmail authentication failed. Check the App Password.")
    raise SystemExit(1)
except smtplib.SMTPRecipientsRefused:
    print("✗ Email failed")
    print("Reason: recipient email was rejected.")
    raise SystemExit(1)
except (smtplib.SMTPException, OSError):
    print("✗ Email failed")
    print("Reason: could not connect to or send through Gmail SMTP.")
    raise SystemExit(1)
