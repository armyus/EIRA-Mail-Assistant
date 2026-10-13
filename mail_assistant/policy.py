"""Validate model suggestions before any application can act on them."""

from __future__ import annotations

import math
from dataclasses import dataclass


CATEGORY_LABELS = frozenset(
    {
        "Needs a reply",
        "Action needed",
        "Informational",
        "Newsletter or promotion",
        "Urgent or time-sensitive",
    }
)
REVIEW_LABEL = "Needs review"
DEFAULT_MIN_CONFIDENCE = 0.75


@dataclass(frozen=True)
class Decision:
    """A checked suggestion; this prototype does not perform Gmail actions."""

    labels: tuple[str, ...]
    needs_reply: bool
    draft_body: str | None
    confidence: float | None
    requires_review: bool
    reasons: tuple[str, ...] = ()


def _review(reason: str, confidence: float | None = None) -> Decision:
    return Decision(
        labels=(REVIEW_LABEL,),
        needs_reply=False,
        draft_body=None,
        confidence=confidence,
        requires_review=True,
        reasons=(reason,),
    )


def validate_suggestion(
    suggestion: object,
    minimum_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> Decision:
    """Check shape and basic invariants; a passing result is still only a suggestion.

    Model-reported confidence is not proof of correctness. The minimum is a
    provisional filter and must be evaluated before it can drive automation.
    """
    if not isinstance(suggestion, dict):
        return _review("Model output was not a JSON object.")

    labels = suggestion.get("labels")
    if not isinstance(labels, list) or not labels:
        return _review("Model output must contain at least one category label.")
    if any(not isinstance(label, str) or label not in CATEGORY_LABELS for label in labels):
        return _review("Model output contained an unknown category label.")
    if len(set(labels)) != len(labels):
        return _review("Model output contained duplicate labels.")

    confidence = suggestion.get("confidence")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not math.isfinite(confidence)
        or not 0 <= confidence <= 1
    ):
        return _review("Model output contained an invalid confidence value.")
    confidence = float(confidence)
    if confidence < minimum_confidence:
        return _review("Model confidence was below the provisional threshold.", confidence)

    needs_reply = suggestion.get("needs_reply")
    if not isinstance(needs_reply, bool):
        return _review("Model output must state whether a reply is needed.", confidence)

    draft_body = suggestion.get("draft_body")
    if draft_body is not None and not isinstance(draft_body, str):
        return _review("Draft body must be text or null.", confidence)
    if needs_reply and (not isinstance(draft_body, str) or not draft_body.strip()):
        return _review("A reply was needed, but the model did not provide a draft.", confidence)
    if not needs_reply and draft_body is not None:
        return _review("The model supplied a draft for a message marked as not needing a reply.", confidence)

    normalized_labels = list(labels)
    if needs_reply and "Needs a reply" not in normalized_labels:
        normalized_labels.append("Needs a reply")

    return Decision(
        labels=tuple(normalized_labels),
        needs_reply=needs_reply,
        draft_body=draft_body.strip() if isinstance(draft_body, str) else None,
        confidence=confidence,
        requires_review=False,
    )
