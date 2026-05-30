"""Serviço de email via SMTP — sem dependências externas além da stdlib."""
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
import structlog

log = structlog.get_logger()


def _build_html_prazo(descricao: str, dias: int, data_prazo: str, link: str) -> str:
    urgencia_color = "#DC2626" if dias <= 3 else "#D97706" if dias <= 7 else "#B8954A"
    urgencia_label = "URGENTE" if dias <= 3 else "ATENÇÃO" if dias <= 7 else "LEMBRETE"
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width"></head>
<body style="margin:0;padding:0;background:#F4F0EA;font-family:'Helvetica Neue',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#F4F0EA;padding:40px 20px;">
  <tr><td align="center">
    <table width="580" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:4px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
      <!-- Header -->
      <tr><td style="background:#1E2229;padding:24px 32px;text-align:center;">
        <span style="color:#B8954A;font-size:20px;font-weight:700;letter-spacing:0.15em;">AFJ CORE</span>
        <span style="color:#F4F0EA;font-size:10px;display:block;letter-spacing:0.2em;margin-top:4px;opacity:0.6;">ALMEIDA, FREIRE & JUCÁ ADVOGADOS</span>
      </td></tr>
      <!-- Badge -->
      <tr><td style="padding:32px 32px 16px;text-align:center;">
        <span style="background:{urgencia_color};color:#fff;font-size:11px;font-weight:700;letter-spacing:0.12em;padding:6px 16px;border-radius:2px;">{urgencia_label} — PRAZO EM {dias} DIA{'S' if dias != 1 else ''}</span>
      </td></tr>
      <!-- Body -->
      <tr><td style="padding:8px 32px 32px;">
        <h2 style="color:#1A1A1A;font-size:18px;margin:0 0 12px;">{descricao}</h2>
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#F4F0EA;border-radius:4px;padding:16px;margin:16px 0;">
          <tr>
            <td style="color:#6B6B6B;font-size:12px;padding:4px 0;">Data do prazo</td>
            <td align="right" style="color:#1A1A1A;font-size:13px;font-weight:600;padding:4px 0;">{data_prazo}</td>
          </tr>
          <tr>
            <td style="color:#6B6B6B;font-size:12px;padding:4px 0;">Tempo restante</td>
            <td align="right" style="color:{urgencia_color};font-size:13px;font-weight:600;padding:4px 0;">{dias} dia{'s' if dias != 1 else ''}</td>
          </tr>
        </table>
        <a href="{link}" style="display:inline-block;background:#B8954A;color:#fff;text-decoration:none;padding:12px 28px;border-radius:2px;font-size:13px;font-weight:600;letter-spacing:0.05em;margin-top:8px;">Ver Processo →</a>
      </td></tr>
      <!-- Footer -->
      <tr><td style="border-top:1px solid #EAE5D8;padding:16px 32px;text-align:center;">
        <span style="color:#B0A898;font-size:11px;">AFJ CORE SYSTEM — Sistema Jurídico Inteligente</span>
      </td></tr>
    </table>
  </td></tr>
</table>
</body>
</html>"""


async def send_email(
    to: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
) -> bool:
    from app.config import settings
    if not settings.EMAIL_ENABLED or not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        log.debug("email_skipped", reason="email not configured", to=to, subject=subject)
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM}>"
    msg["To"] = to

    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM, to, msg.as_string())
        log.info("email_sent", to=to, subject=subject)
        return True
    except Exception as exc:
        log.warning("email_failed", to=to, subject=subject, error=str(exc))
        return False


async def send_prazo_alert(
    to_email: str,
    descricao: str,
    dias: int,
    data_prazo: str,
    base_url: str = "https://afj.sistema.com.br",
    process_id: str = "",
) -> bool:
    link = f"{base_url}/processos/{process_id}" if process_id else base_url
    subject = f"[AFJ CORE] {'🚨 URGENTE' if dias <= 3 else '⚠️ ATENÇÃO'} — Prazo em {dias} dia{'s' if dias != 1 else ''}: {descricao[:60]}"
    html = _build_html_prazo(descricao, dias, data_prazo, link)
    text = f"AFJ CORE — Prazo em {dias} dia(s)\n\n{descricao}\nData: {data_prazo}\nLink: {link}"
    return await send_email(to_email, subject, html, text)
