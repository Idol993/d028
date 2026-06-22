import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Any, Dict, List, Optional
from pathlib import Path

import requests

from .config_loader import ConfigLoader
from .audit_logger import AuditLogger


class NotificationManager:
    def __init__(self):
        self.config = ConfigLoader()
        self.logger = AuditLogger()

    def send_notification(self, title: str, content: str,
                          channels: Optional[List[str]] = None,
                          attachments: Optional[List[str]] = None) -> Dict[str, bool]:
        if channels is None:
            channels = self.config.get("notification", {}).keys()

        results = {}
        for channel in channels:
            try:
                if channel == "wecom" and self.config.get("notification.wecom.enabled", False):
                    results["wecom"] = self._send_wecom(title, content)
                elif channel == "dingtalk" and self.config.get("notification.dingtalk.enabled", False):
                    results["dingtalk"] = self._send_dingtalk(title, content)
                elif channel == "email" and self.config.get("notification.email.enabled", False):
                    results["email"] = self._send_email(title, content, attachments)
            except Exception as e:
                self.logger.error(f"Failed to send {channel} notification: {e}", exc_info=True)
                results[channel] = False

        return results

    def _send_wecom(self, title: str, content: str) -> bool:
        webhook_url = self.config.get("notification.wecom.webhook_url")
        if not webhook_url or "${" in webhook_url:
            self.logger.warning("WeCom webhook URL not configured, skipping")
            return False

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": f"## {title}\n\n{content}"
            }
        }

        response = requests.post(webhook_url, json=payload, timeout=10)
        success = response.status_code == 200 and response.json().get("errcode", -1) == 0

        if success:
            self.logger.audit("notification", "system", "wecom", "success",
                              {"title": title})
        else:
            self.logger.warning(f"WeCom notification failed: {response.text}")

        return success

    def _send_dingtalk(self, title: str, content: str) -> bool:
        webhook_url = self.config.get("notification.dingtalk.webhook_url")
        if not webhook_url or "${" in webhook_url:
            self.logger.warning("DingTalk webhook URL not configured, skipping")
            return False

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": f"## {title}\n\n{content}"
            }
        }

        response = requests.post(webhook_url, json=payload, timeout=10)
        success = response.status_code == 200 and response.json().get("errcode", -1) == 0

        if success:
            self.logger.audit("notification", "system", "dingtalk", "success",
                              {"title": title})
        else:
            self.logger.warning(f"DingTalk notification failed: {response.text}")

        return success

    def _send_email(self, title: str, content: str,
                    attachments: Optional[List[str]] = None) -> bool:
        email_config = self.config.get("notification.email", {})
        smtp_host = email_config.get("smtp_host", "")
        if "${" in smtp_host:
            self.logger.warning("Email SMTP not configured, skipping")
            return False

        smtp_port = email_config.get("smtp_port", 587)
        username = email_config.get("username", "")
        password = email_config.get("password", "")
        recipients = email_config.get("recipients", [])

        if not all([smtp_host, username, password, recipients]):
            self.logger.warning("Email configuration incomplete, skipping")
            return False

        try:
            msg = MIMEMultipart()
            msg["From"] = username
            msg["To"] = ", ".join(recipients)
            msg["Subject"] = title

            msg.attach(MIMEText(content, "html", "utf-8"))

            if attachments:
                for attachment_path in attachments:
                    path = Path(attachment_path)
                    if path.exists():
                        with open(path, "rb") as f:
                            part = MIMEBase("application", "octet-stream")
                            part.set_payload(f.read())
                        encoders.encode_base64(part)
                        part.add_header(
                            "Content-Disposition",
                            f"attachment; filename= {path.name}"
                        )
                        msg.attach(part)

            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
                server.starttls()
                server.login(username, password)
                server.send_message(msg)

            self.logger.audit("notification", "system", "email", "success",
                              {"title": title, "recipients": recipients})
            return True

        except Exception as e:
            self.logger.error(f"Email send failed: {e}", exc_info=True)
            return False
