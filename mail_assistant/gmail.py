"""Narrow Gmail API adapter: read messages, apply labels, and create drafts."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.policy import default
from email.utils import getaddresses
from html.parser import HTMLParser
from pathlib import Path


GMAIL_MODIFY_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
LABEL_PREFIX = "EIRA/"
MAX_BODY_CHARS = 16_000


@dataclass(frozen=True)
class MailMessage:
    message_id: str
    thread_id: str
    sender: str
    reply_to: str
    subject: str
    body: str
    message_id_header: str
    references: str
    internal_date_ms: int


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except (LookupError, UnicodeError, ValueError):
        return value


def _decode_part(data: str) -> str:
    raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    return raw.decode("utf-8", errors="replace")


def _collect_bodies(payload: dict[str, object]) -> tuple[list[str], list[str]]:
    plain: list[str] = []
    html: list[str] = []
    mime = str(payload.get("mimeType", ""))
    body_info = payload.get("body")
    if isinstance(body_info, dict) and isinstance(body_info.get("data"), str):
        text = _decode_part(str(body_info["data"]))
        if mime == "text/plain":
            plain.append(text)
        elif mime == "text/html":
            html.append(text)
    parts = payload.get("parts", [])
    if isinstance(parts, list):
        for part in parts:
            if isinstance(part, dict):
                child_plain, child_html = _collect_bodies(part)
                plain.extend(child_plain)
                html.extend(child_html)
    return plain, html


def parse_gmail_message(resource: dict[str, object]) -> MailMessage:
    payload = resource.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("Gmail returned a message without a MIME payload.")
    raw_headers = payload.get("headers", [])
    headers: dict[str, str] = {}
    if isinstance(raw_headers, list):
        for item in raw_headers:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                name = str(item["name"]).casefold()
                headers[name] = _decode_header(str(item.get("value", "")))
    plain_parts, html_parts = _collect_bodies(payload)
    if plain_parts:
        body = "\n\n".join(plain_parts)
    elif html_parts:
        extractor = _TextExtractor()
        extractor.feed("\n".join(html_parts))
        body = "\n".join(extractor.parts)
    else:
        body = ""
    body = re.sub(r"\n{3,}", "\n\n", body).strip()[:MAX_BODY_CHARS]
    return MailMessage(
        message_id=str(resource.get("id", "")),
        thread_id=str(resource.get("threadId", "")),
        sender=headers.get("from", ""),
        reply_to=headers.get("reply-to", headers.get("from", "")),
        subject=headers.get("subject", "(no subject)"),
        body=body,
        message_id_header=headers.get("message-id", ""),
        references=headers.get("references", ""),
        internal_date_ms=int(resource.get("internalDate", "0")),
    )


def build_gmail_service(credentials_path: Path, token_path: Path):
    """Load desktop OAuth credentials and create the Gmail API client."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as error:
        raise RuntimeError(
            "Gmail libraries are not installed. Install requirements.txt in .venv first."
        ) from error

    credentials = None
    if token_path.exists():
        credentials = Credentials.from_authorized_user_file(str(token_path), [GMAIL_MODIFY_SCOPE])
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        token_path.write_text(credentials.to_json(), encoding="utf-8")
    if not credentials or not credentials.valid:
        if not credentials_path.exists():
            raise RuntimeError(
                "OAuth credentials are missing. Download a Desktop OAuth client as "
                "credentials.json and place it in the project folder."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), [GMAIL_MODIFY_SCOPE])
        credentials = flow.run_local_server(port=0, open_browser=True)
        token_path.write_text(credentials.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def list_messages(service, *, after_epoch: int | None, max_results: int = 30) -> list[str]:
    query = "in:inbox -from:me"
    if after_epoch is not None:
        query += f" after:{max(0, after_epoch - 1)}"
    message_ids: list[str] = []
    page_token: str | None = None
    while True:
        request_args: dict[str, object] = {"userId": "me", "q": query, "maxResults": max_results}
        if page_token:
            request_args["pageToken"] = page_token
        result = service.users().messages().list(**request_args).execute()
        message_ids.extend(
            str(row["id"]) for row in result.get("messages", []) if row.get("id")
        )
        page_token = result.get("nextPageToken")
        if not page_token:
            return message_ids


def get_message(service, message_id: str) -> MailMessage:
    result = service.users().messages().get(
        userId="me", id=message_id, format="full"
    ).execute()
    return parse_gmail_message(result)


def ensure_category_labels(service, category_names: set[str]) -> dict[str, str]:
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    existing = {str(label["name"]): str(label["id"]) for label in labels if label.get("name") and label.get("id")}
    result: dict[str, str] = {}
    for category in sorted(category_names):
        full_name = LABEL_PREFIX + category
        label_id = existing.get(full_name)
        if label_id is None:
            created = service.users().labels().create(
                userId="me",
                body={"name": full_name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
            ).execute()
            label_id = str(created["id"])
        result[category] = label_id
    return result


def apply_labels(service, message_id: str, label_ids: list[str]) -> None:
    if label_ids:
        service.users().messages().modify(
            userId="me", id=message_id, body={"addLabelIds": label_ids}
        ).execute()


def create_reply_draft(service, message: MailMessage, body: str) -> str:
    if not message.thread_id:
        raise ValueError("Gmail did not provide a thread ID; no draft was created.")
    recipients = [address for _, address in getaddresses([message.reply_to]) if address]
    if not recipients:
        raise ValueError("Could not determine a reply address; no draft was created.")
    draft_email = EmailMessage(policy=default)
    draft_email["To"] = recipients[0]
    subject = message.subject.strip()
    draft_email["Subject"] = subject if subject.casefold().startswith("re:") else f"Re: {subject}"
    if message.message_id_header:
        draft_email["In-Reply-To"] = message.message_id_header
        references = " ".join(filter(None, (message.references, message.message_id_header)))
        draft_email["References"] = references
    draft_email.set_content(body)
    raw = base64.urlsafe_b64encode(draft_email.as_bytes()).decode("ascii").rstrip("=")
    result = service.users().drafts().create(
        userId="me", body={"message": {"raw": raw, "threadId": message.thread_id}}
    ).execute()
    return str(result.get("id", ""))
