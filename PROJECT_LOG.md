# EIRA Project Log

## Current status

- Personal Gmail assistant for one account; Gmail OAuth is configured locally.
- Five-minute watch mode can label messages and create unsent reply drafts. It has processed real inbox messages; no automatic send path exists.
- Telegram bot and chat configuration were set in the user's PowerShell environment. Telegram sends aggregate status/action text only.
- Latest code change: send a Telegram update after every completed watch check, including no new mail, and after a failed Gmail check. The owner restarted the watcher; next confirm a Telegram status arrives.
- Latest real-message behavior observed before that change: a message was marked **Needs review**, no reply draft was created, and the watcher was stopped.

## Product decisions

- First version is only for the project owner.
- Python rules control message categories and whether a reply draft is made. The local Qwen 3.5 0.8B model contributes wording only.
- Unknown facts use an explicit placeholder. Unclear requests receive **Needs review** and no draft.
- An urgency label may accompany **Needs review** when an urgency signal is clear but reply intent is not.
- Drafts remain unsent for owner review; EIRA does not send, delete, archive, or forward email.
- Telegram notifications contain counts and action status only, never email content or identifying details.
- WhatsApp was deferred while Telegram is used for development notifications.

## Implemented

- Local Python project environment and Ollama model setup.
- Rule-first classifier, safe draft fallback, policy validation, and synthetic evaluation.
- Gmail API parsing, labels, in-thread draft creation, preview mode, explicit apply mode, and five-minute watch mode.
- Local SQLite checkpoint and duplicate-prevention store.
- Gmail OAuth credential files are local and ignored by Git.
- Optional Telegram Bot API notifier, disabled unless both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are configured.
- The watcher now reports every completed check to Telegram, including no-new-mail checks; failed Gmail checks also send a retry status.
- Removed generated project `__pycache__` directories, empty `.qodo` scaffolding, and the unused WhatsApp notifier module. Kept runtime dependencies, OAuth files, local processing state, test cases, and tests.
- The last recorded synthetic evaluation passed 13/13 cases. This was before the most recent urgency and per-check notification changes; those changes have not been tested yet.

## Important constraints

- Gmail's `gmail.modify` OAuth scope permits sending as well as reading, labeling, and creating drafts. The application has no send implementation.
- Messages are not reprocessed automatically after a rule change because the SQLite store suppresses duplicate processing. An already processed message may need manual label correction.
- The 13-case synthetic evaluation is small and cannot establish real-world classification reliability.
- Keep Gmail OAuth files and Telegram bot tokens private; do not put them in source files or chat.

