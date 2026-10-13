"""Conservative, deterministic first-pass email intent classification."""

from __future__ import annotations

import re

from mail_assistant.policy import Decision, REVIEW_LABEL


_INJECTION_MARKERS = (
    "ignore all prior instructions",
    "ignore previous instructions",
    "disregard all previous instructions",
)
_NO_ACTION = (
    "no further action is needed",
    "no action is needed",
    "no action required",
    "for your information",
    "this is to confirm that we received",
)
_NEWSLETTER = ("newsletter", "weekly digest", "product digest", "unsubscribe", "new articles")
_AUTOMATED_SENDER = re.compile(
    r"\b(?:no[-_.]?reply|do[-_.]?not[-_.]?reply)\s*@",
    re.IGNORECASE,
)
_AUTOMATED_ALERT = re.compile(
    r"\b(?:job alert|opportunities for you|recommended for you|"
    r"(?:picked|found|matched)\b.{0,60}\b(?:opportunities|jobs|roles))\b",
    re.IGNORECASE,
)
_REQUEST = re.compile(
    r"\b(please\s+(confirm|reply|respond|review|send|provide|approve|let me know)|"
    r"could you|can you|would you|are you available|do you approve|"
    r"tell me whether|need your (response|approval|decision))\b",
    re.IGNORECASE,
)
_ACTION_REQUEST = re.compile(
    r"\b(please\s+(confirm|reply|respond|review|send|provide|approve|let (me|us) know)|"
    r"could you|can you|would you|tell me whether|need your (response|approval|decision))\b",
    re.IGNORECASE,
)
_DEADLINE = re.compile(
    r"\b(urgent|asap|immediately|by\s+(\d{1,2}(?::\d{2})?\s*(am|pm)?|today|tomorrow|end of day))\b",
    re.IGNORECASE,
)


def classify_email(*, sender: str, subject: str, body: str) -> Decision:
    """Classify clear cases without trusting model-reported labels or confidence.

    Deliberately returns Needs review when the message does not match a narrow,
    recognizable pattern. This is a first-pass rule set, not a general email AI.
    """
    full_text = f"{sender}\n{subject}\n{body}"
    lower = full_text.casefold()
    # Ignore text that looks like an attempt to change the assistant's rules.
    intent_text = body
    for marker in _INJECTION_MARKERS:
        marker_at = intent_text.casefold().find(marker)
        if marker_at >= 0:
            intent_text = intent_text[:marker_at]
            break
    intent = f"{subject}\n{intent_text}"
    intent_lower = intent.casefold()

    if any(term in lower for term in _NEWSLETTER):
        return Decision(("Newsletter or promotion",), False, None, None, False)

    if any(term in intent_lower for term in _NO_ACTION):
        return Decision(("Informational",), False, None, None, False)

    # Job/opportunity digests sent from a no-reply address are notifications,
    # even when their templates contain rhetorical questions. Other automated
    # messages stay in review so we never draft a reply to a mailbox that cannot
    # receive one.
    if _AUTOMATED_SENDER.search(sender):
        if _AUTOMATED_ALERT.search(f"{subject}\n{body}"):
            return Decision(("Newsletter or promotion",), False, None, None, False)
        return Decision((REVIEW_LABEL,), False, None, None, True,
                        ("Automated sender; verify whether a reply is appropriate.",))

    asks_for_reply = bool(_REQUEST.search(intent)) or "?" in intent
    if not asks_for_reply:
        # Retain a clear urgency signal even when there is not enough context
        # to decide whether a reply is needed. Mark it for human review and do
        # not create a draft based on an urgent subject alone.
        labels = [REVIEW_LABEL]
        if _DEADLINE.search(intent):
            labels.insert(0, "Urgent or time-sensitive")
        return Decision(tuple(labels), False, None, None, True,
                        ("No clear reply-needed signal matched the local rules.",))

    labels = ["Needs a reply"]
    if _ACTION_REQUEST.search(intent):
        labels.append("Action needed")
    if _DEADLINE.search(intent):
        labels.append("Urgent or time-sensitive")
    return Decision(tuple(labels), True, None, None, False)


def placeholder_draft(body: str) -> str:
    """Create a fact-safe draft that never claims an unknown decision or status."""
    lower = body.casefold()
    if "available" in lower or "availability" in lower:
        missing = "your availability"
    elif any(word in lower for word in ("approve", "approval", "proceed", "decision")):
        missing = "your decision or approval"
    elif any(word in lower for word in ("send", "provide", "share")):
        missing = "the requested information or attachment"
    else:
        missing = "your response to the request"
    casual = lower.lstrip().startswith(("hey", "hi ", "hiya", "yo")) or any(
        phrase in lower for phrase in ("when you get a sec", "when you get a chance", "what's up")
    )
    if casual:
        return (
            "Hey,\n\nThanks for the message! "
            f"[PLEASE CONFIRM: {missing}]\n\nTalk soon,\n[Your name]"
        )
    return (
        "Hello,\n\nThank you for reaching out. "
        f"[PLEASE CONFIRM: {missing}]\n\nBest,\n[Your name]"
    )
