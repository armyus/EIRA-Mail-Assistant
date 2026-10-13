"""Personal Gmail draft assistant. Mailbox writes require an explicit --apply."""

from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path

from mail_assistant.drafting import create_reply_draft
from mail_assistant.gmail import (
    MailMessage,
    apply_labels,
    build_gmail_service,
    create_reply_draft as gmail_create_reply_draft,
    ensure_category_labels,
    get_message,
    list_messages,
)
from mail_assistant.policy import REVIEW_LABEL
from mail_assistant.rules import classify_email
from mail_assistant.store import ProcessStore
from mail_assistant.telegram import send_action_summary


ROOT = Path(__file__).resolve().parents[1]
POLL_SECONDS = 300


def _parse_since(value: str) -> int:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use a date like 2026-10-12 or an ISO date/time.") from error
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return int(parsed.timestamp())


def _draft_text(message: MailMessage) -> str:
    return create_reply_draft(
        sender=message.sender,
        subject=message.subject,
        body=message.body,
    )


def run_once(
    service,
    store: ProcessStore,
    *,
    after_epoch: int | None,
    apply: bool,
    max_results: int,
    summary_only: bool = False,
    notify_idle: bool = False,
) -> int:
    message_ids = list_messages(service, after_epoch=after_epoch, max_results=max_results)
    pending: list[tuple[MailMessage, tuple[str, ...], str | None]] = []
    for message_id in message_ids:
        if apply and store.contains(message_id):
            continue
        message = get_message(service, message_id)
        decision = classify_email(sender=message.sender, subject=message.subject, body=message.body)
        labels = decision.labels
        if decision.requires_review and REVIEW_LABEL not in labels:
            labels = (*labels, REVIEW_LABEL)
        draft = _draft_text(message) if decision.needs_reply else None
        pending.append((message, labels, draft))

    if apply and pending:
        label_ids = ensure_category_labels(
            service, {label for _, labels, _ in pending for label in labels}
        )

    changed = 0
    summary: dict[str, int] = {}
    draft_count = 0
    applied_summary: dict[str, int] = {}
    applied_drafts = 0
    failed_count = 0
    for message, labels, draft in pending:
        for label in labels:
            summary[label] = summary.get(label, 0) + 1
        if draft:
            draft_count += 1
        if not summary_only:
            print(f"From: {message.sender or '(unknown sender)'}")
            print(f"Subject: {message.subject}")
            print(f"Labels: {', '.join(labels)}")
            if draft:
                print("Draft preview:")
                print(draft)
        if not apply:
            if not summary_only:
                print("Preview only; Gmail was not changed.\n")
            continue
        if not store.claim(message.message_id):
            if not summary_only:
                print("Skipped: this message was already processed or needs recovery.\n")
            continue
        try:
            api_label_ids = [label_ids[label] for label in labels]
            apply_labels(service, message.message_id, api_label_ids)
            draft_id = gmail_create_reply_draft(service, message, draft) if draft else ""
            store.finish(message.message_id, "done", f"draft_id={draft_id}" if draft_id else "labels applied")
            changed += 1
            applied_drafts += int(bool(draft_id))
            for label in labels:
                applied_summary[label] = applied_summary.get(label, 0) + 1
            if not summary_only:
                print("Applied labels and created an unsent draft." if draft else "Applied labels; no reply draft needed.")
        except Exception as error:
            store.finish(message.message_id, "failed", str(error))
            failed_count += 1
            if not summary_only:
                print(f"Processing failed and was not retried automatically: {error}")
        if not summary_only:
            print()
    if apply and (changed or failed_count or notify_idle):
        if changed or failed_count:
            label_totals = ", ".join(
                f"{label}: {count}" for label, count in sorted(applied_summary.items())
            ) or "none"
            action_summary = (
                f"EIRA checked Gmail. Emails processed: {changed}; processing failures: {failed_count}. "
                f"Labels applied: {label_totals}. Unsent drafts created: {applied_drafts}."
            )
        else:
            action_summary = "EIRA checked Gmail. No new messages to process."
        try:
            if send_action_summary(summary=action_summary):
                print("Telegram action summary sent.")
        except Exception as error:
            print(f"Gmail actions completed, but Telegram summary failed: {error}")
    if summary_only:
        print(f"Previewed {len(pending)} messages. Gmail was not changed.")
        print(f"Draft candidates: {draft_count}")
        for label, count in sorted(summary.items()):
            print(f"{label}: {count}")
    elif not pending:
        print("No matching inbox messages.")
    return changed


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify Gmail messages and prepare unsent reply drafts.")
    parser.add_argument("--apply", action="store_true", help="Apply category labels and create unsent Gmail drafts.")
    parser.add_argument("--watch", action="store_true", help="Check for new messages every five minutes.")
    parser.add_argument("--check-connection", action="store_true", help="Verify Gmail access without reading message contents or changing the mailbox.")
    parser.add_argument("--summary-only", action="store_true", help="Preview aggregate label counts without printing sender, subject, or draft text.")
    parser.add_argument("--since", type=_parse_since, help="Only process messages after this date/time (required for one-time runs).")
    parser.add_argument("--max-results", type=int, default=30, help="Gmail API page size (default: 30).")
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    if args.check_connection and (args.apply or args.watch or args.since is not None or args.summary_only):
        print("--check-connection cannot be combined with mailbox processing options.")
        return 2
    if args.summary_only and (args.apply or args.watch):
        print("--summary-only is available for one-time preview runs only.")
        return 2
    if args.max_results < 1 or args.max_results > 100:
        print("--max-results must be between 1 and 100.")
        return 2
    if not args.watch and args.since is None and not args.check_connection:
        print("One-time runs require --since DATE so the date range is explicit.")
        return 2

    state_path = ROOT / ".state" / "processed.sqlite3"
    store = ProcessStore(state_path)
    try:
        service = build_gmail_service(ROOT / "credentials.json", ROOT / "token.json")
    except Exception as error:
        print(error)
        return 2

    if args.check_connection:
        try:
            service.users().getProfile(userId="me").execute()
        except Exception as error:
            print(f"Gmail authorization check failed: {error}")
            return 1
        print("Gmail authorization works. No messages were read and the mailbox was not changed.")
        return 0

    if not args.watch:
        try:
            run_once(service, store, after_epoch=args.since, apply=args.apply, max_results=args.max_results, summary_only=args.summary_only)
        except Exception as error:
            print(f"Gmail check failed; no checkpoint was advanced: {error}")
            return 1
        return 0

    if args.since is not None:
        checkpoint = args.since
        store.set_checkpoint(checkpoint)
    else:
        checkpoint = store.checkpoint()
    if checkpoint is None:
        checkpoint = int(time.time())
        store.set_checkpoint(checkpoint)
        print("Started a fresh watch from now; older email will not be processed.")

    print(f"Watching Gmail every {POLL_SECONDS // 60} minutes. Press Ctrl+C to stop.")
    try:
        while True:
            started = int(time.time())
            try:
                run_once(
                    service,
                    store,
                    after_epoch=checkpoint,
                    apply=args.apply,
                    max_results=args.max_results,
                    notify_idle=args.apply,
                )
            except Exception as error:
                print(f"Gmail check failed; will retry after the next interval: {error}")
                if args.apply:
                    try:
                        if send_action_summary(
                            summary="EIRA could not complete this Gmail check. It will retry in five minutes."
                        ):
                            print("Telegram check-failure notice sent.")
                    except Exception as notification_error:
                        print(f"Telegram status notification failed: {notification_error}")
                time.sleep(POLL_SECONDS)
                continue
            checkpoint = started
            store.set_checkpoint(checkpoint)
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("Stopped Gmail watch.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
