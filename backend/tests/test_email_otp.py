import smtplib
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from app.email_otp import send_registration_code


class EmailDeliveryTests(unittest.TestCase):
    @patch.dict("os.environ", {"SMTP_HOST": "smtp.example.test", "SMTP_FROM": "no-reply@example.test", "SMTP_USERNAME": "user", "SMTP_PASSWORD": "test-password", "SMTP_SECURITY": "starttls", "SMTP_PORT": "587"})
    @patch("app.email_otp.smtplib.SMTP")
    def test_starttls_email_delivery(self, client):
        smtp = client.return_value.__enter__.return_value
        smtp.send_message.return_value = {}
        send_registration_code("student@example.test", "123456")
        client.assert_called_once_with("smtp.example.test", 587, timeout=10)
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("user", "test-password")
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["To"], "student@example.test")
        self.assertIn("123456", message.get_content())

    @patch.dict("os.environ", {"SMTP_HOST": "smtp.example.test", "SMTP_FROM": "no-reply@example.test", "SMTP_USERNAME": "", "SMTP_PASSWORD": "", "SMTP_SECURITY": "ssl", "SMTP_PORT": "465"})
    @patch("app.email_otp.smtplib.SMTP_SSL")
    def test_delivery_failure_returns_service_unavailable(self, client):
        client.side_effect = smtplib.SMTPException("provider details")
        with self.assertRaises(HTTPException) as caught:
            send_registration_code("student@example.test", "123456")
        self.assertEqual(caught.exception.status_code, 503)
        self.assertNotIn("provider details", caught.exception.detail)
