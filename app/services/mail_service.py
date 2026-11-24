import os
import ssl
from email.message import EmailMessage
from pathlib import Path

import aiosmtplib
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Templates directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "app" / "templates"

jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "jinja"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


class MailService:
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.fastmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")

    async def send(self, to_email: str, subject: str, template_name: str, **context) -> None:
        """Send an email using a Jinja2 template."""
        template = jinja_env.get_template(template_name)
        html_content = template.render(**context)

        message = EmailMessage()
        message["From"] = f"CORE <{self.smtp_user}>"
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content("Your verification code")  # plain text fallback
        message.add_alternative(html_content, subtype="html")

        context_obj = ssl.create_default_context()
        async with aiosmtplib.SMTP(
            hostname=self.smtp_host,
            port=self.smtp_port,
            start_tls=True,
            ssl_context=context_obj,
        ) as smtp:
            await smtp.login(self.smtp_user, self.smtp_password)
            await smtp.send_message(message)

    async def send_verification_code(self, to_email: str, code: str) -> None:
        """Send a verification code email."""
        html_content = await jinja_env.get_template("verification_email.html").render(code=code)

        message = EmailMessage()
        message["From"] = f"CORE <{self.smtp_user}>"
        message["To"] = to_email
        message["Subject"] = "Your CORE Verification Code"
        message.set_content("Your verification code is: " + code)
        message.add_alternative(html_content, subtype="html")

        context_obj = ssl.create_default_context()
        async with aiosmtplib.SMTP(
            hostname=self.smtp_host,
            port=self.smtp_port,
            start_tls=True,
            ssl_context=context_obj,
        ) as smtp:
            await smtp.login(self.smtp_user, self.smtp_password)
            await smtp.send_message(message)