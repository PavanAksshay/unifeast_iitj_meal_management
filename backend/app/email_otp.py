"""Send registration codes through the configured SMTP email service."""
import os
import smtplib
import ssl
from email.message import EmailMessage

from fastapi import HTTPException


def send_registration_code(email: str, code: str) -> None:
    host = os.getenv("SMTP_HOST", "").strip()
    sender = os.getenv("SMTP_FROM", "").strip()
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")
    security = os.getenv("SMTP_SECURITY", "starttls")
    if not host or not sender:
        raise HTTPException(503, "Email verification is awaiting configuration. Contact the administrator.")
    if security not in {"starttls", "ssl"} or bool(username) != bool(password):
        raise HTTPException(503, "Email verification configuration is incomplete. Contact the administrator.")
    try:
        port = int(os.getenv("SMTP_PORT", "465" if security == "ssl" else "587"))
    except ValueError as error:
        raise HTTPException(503, "Email verification configuration is incomplete. Contact the administrator.") from error
    smtp_client = smtplib.SMTP_SSL if security == "ssl" else smtplib.SMTP
    connection_options = {"timeout": 10}
    if security == "ssl":
        connection_options["context"] = ssl.create_default_context()
    try:
        message = EmailMessage()
        message["Subject"] = "Your UniFeast email verification code"
        message["From"] = sender
        message["To"] = email
        message.set_content(f"Your UniFeast verification code is {code}.\n\nIt expires in 5 minutes. If you did not request this code, ignore this email.")
        with smtp_client(host, port, **connection_options) as smtp:
            if security == "starttls":
                smtp.starttls(context=ssl.create_default_context())
            if username:
                smtp.login(username, password)
            if smtp.send_message(message):
                raise smtplib.SMTPException("Email recipient refused")
    except (OSError, ValueError, smtplib.SMTPException) as error:
        raise HTTPException(503, "Could not send the verification email. Please try again later.") from error
