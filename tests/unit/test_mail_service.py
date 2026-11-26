import ssl
from types import SimpleNamespace

import pytest

from app.services import mail_service


class FakeSMTP:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.sent_message = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def login(self, _username, _password):
        return None

    async def send_message(self, message):
        self.sent_message = message


@pytest.mark.asyncio
async def test_verification_email_uses_supported_tls_context(monkeypatch):
    monkeypatch.setattr(
        mail_service,
        "smtp_setting",
        SimpleNamespace(
            smtp_host="smtp.example.test",
            smtp_port=587,
            smtp_user="sender@example.test",
            smtp_password="test-password",
        ),
    )
    smtp = FakeSMTP()
    monkeypatch.setattr(mail_service.aiosmtplib, "SMTP", lambda **kwargs: _smtp_instance(smtp, kwargs))

    await mail_service.MailService().send_verification_code(
        "customer@example.test",
        "012345",
    )

    assert smtp.kwargs["start_tls"] is True
    assert isinstance(smtp.kwargs["tls_context"], ssl.SSLContext)
    assert "ssl_context" not in smtp.kwargs
    assert smtp.sent_message["To"] == "customer@example.test"
    html_body = smtp.sent_message.get_body(preferencelist=("html",)).get_content()
    assert "012345" in html_body
    assert "{code}" not in html_body


def _smtp_instance(smtp, kwargs):
    smtp.kwargs = kwargs
    return smtp
