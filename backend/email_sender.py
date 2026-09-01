"""
Email sender — uses Gmail SMTP with an App Password.
Attaches CV and Cover Letter PDFs to the application email.
"""
import smtplib
import ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from config import settings

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def send_application(
    to_email: str,
    subject: str,
    body: str,
    cv_path: Optional[Path] = None,
    cover_letter_path: Optional[Path] = None,
) -> bool:
    """
    Send the application email with optional PDF attachments.
    Returns True on success, raises on failure.
    """
    msg = MIMEMultipart()
    msg["From"] = settings.gmail_from
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    for path, filename in [
        (cv_path, "CV_Hedi_Bou_Maiza.pdf"),
        (cover_letter_path, "Cover_Letter_Hedi_Bou_Maiza.pdf"),
    ]:
        if path and Path(path).exists():
            with open(path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
            msg.attach(part)

    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls(context=context)
        server.login(settings.gmail_from, settings.gmail_app_password)
        server.sendmail(settings.gmail_from, to_email, msg.as_string())

    return True
