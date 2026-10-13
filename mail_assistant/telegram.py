"""Optional Telegram notifications for completed Gmail batches."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class TelegramConfigError(ValueError):
    pass


def send_action_summary(*, summary: str) -> bool:
    """Send an aggregate action summary when Telegram is fully configured.

    Notifications are opt-in and intentionally contain no email content.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token and not chat_id:
        return False
    if not token or not chat_id:
        raise TelegramConfigError(
            "Telegram notification is partially configured; set both "
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."
        )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    request = Request(
        url,
        data=json.dumps({"chat_id": chat_id, "text": summary}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise RuntimeError(f"Telegram API returned HTTP {error.code}.") from None
    except URLError as error:
        raise RuntimeError(f"Telegram notification could not connect: {error.reason}") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("Telegram API returned an unreadable response.") from None
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise RuntimeError("Telegram API did not accept the action summary.")
    return True
