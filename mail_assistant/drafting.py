"""Generate reply wording with the local model and a conservative fallback."""

from __future__ import annotations

import re

from mail_assistant.model import assess_email
from mail_assistant.rules import placeholder_draft


def _required_placeholder(template: str) -> str:
    start = template.index("[PLEASE CONFIRM:")
    end = template.index("]", start) + 1
    return template[start:end]


def create_reply_draft(
    *,
    sender: str,
    subject: str,
    body: str,
    known_facts: dict[str, str] | None = None,
) -> str:
    """Return a reply draft; use a safe template if the model fails basic checks.

    This gate catches a few common failures. It is not a factuality proof, so
    the user must review the resulting Gmail draft before sending it.
    """
    fallback = placeholder_draft(body)
    try:
        candidate = assess_email(
            sender=sender,
            subject=subject,
            body=body,
            known_facts=known_facts,
        ).get("draft_body")
    except (RuntimeError, OSError):
        return fallback
    if not isinstance(candidate, str) or not candidate.strip():
        return fallback

    candidate = candidate.strip()
    required = _required_placeholder(fallback)
    # Reject first-person statements: the small model has previously invented
    # availability and actions even while including a placeholder.
    if required.casefold() not in candidate.casefold():
        return fallback
    if re.search(r"\bI(?:\s|['’])", candidate, re.IGNORECASE):
        return fallback
    return candidate
