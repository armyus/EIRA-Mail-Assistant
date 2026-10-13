"""Run the local model against synthetic cases; no Gmail access is involved."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from mail_assistant.drafting import create_reply_draft
from mail_assistant.rules import classify_email


CASES_PATH = Path(__file__).resolve().parents[1] / "samples" / "evaluation_cases.json"


def evaluate_case(case: dict[str, object]) -> tuple[bool, list[str], str]:
    email = case["email"]
    assert isinstance(email, dict)
    # The model may contribute wording, but Python owns classification and
    # whether a draft exists. Never use its labels, boolean, or confidence.
    decision = classify_email(
        sender=str(email["sender"]),
        subject=str(email["subject"]),
        body=str(email["body"]),
    )
    if decision.needs_reply:
        draft = create_reply_draft(
            sender=str(email["sender"]),
            subject=str(email["subject"]),
            body=str(email["body"]),
            known_facts=case.get("known_facts", {}),  # type: ignore[arg-type]
        )
        decision = replace(decision, draft_body=draft)
    expected_labels = set(case["expected_labels"])  # type: ignore[arg-type]
    reasons: list[str] = []
    expects_review = "Needs review" in expected_labels
    if decision.requires_review and not expects_review:
        detail = "; ".join(decision.reasons) or "local rules could not classify the message"
        reasons.append(f"rules sent this response to Needs review: {detail}")
    if expects_review and not decision.requires_review:
        reasons.append("rules classified a message that should have gone to Needs review")
    if set(decision.labels) != expected_labels:
        reasons.append(f"labels were {list(decision.labels)}, expected {sorted(expected_labels)}")
    if decision.needs_reply != case["expected_needs_reply"]:
        reasons.append(f"needs_reply was {decision.needs_reply}, expected {case['expected_needs_reply']}")

    required_text = case.get("draft_must_contain")
    if required_text:
        draft = decision.draft_body or ""
        if str(required_text).casefold() not in draft.casefold():
            reasons.append(f"draft did not contain required text {required_text!r}")
    if not case["expected_needs_reply"] and decision.draft_body is not None:
        reasons.append("a draft was returned for a message that should not get one")

    return not reasons, reasons, decision.draft_body or "(no draft)"


def main() -> int:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    failures = 0
    for case in cases:
        try:
            passed, reasons, draft = evaluate_case(case)
        except Exception as error:  # Keep one model/API failure from hiding later cases.
            passed, reasons, draft = False, [f"evaluation error: {error}"], "(no draft)"
        marker = "PASS" if passed else "FAIL"
        print(f"{marker} {case['id']}: {case['name']}")
        if not passed:
            failures += 1
            for reason in reasons:
                print(f"  - {reason}")
            print(f"  draft: {draft}")
    print(f"\n{len(cases) - failures}/{len(cases)} cases passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
