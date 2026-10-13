# EIRA: Personal Gmail Assistant

EIRA is a local-first assistant for one Gmail account. It classifies incoming mail, applies Gmail labels, and creates reply drafts for the owner to review. It does not send, delete, archive, or forward email.

## Current behavior

- Checks the inbox every five minutes when watch mode is running.
- Uses deterministic Python rules for labels and reply decisions. The local Qwen 3.5 0.8B model contributes draft wording only.
- Applies overlapping labels when appropriate. Unclear messages get **Needs review** and no draft. A clear urgency signal can be kept alongside **Needs review**.
- Creates unsent drafts only; missing facts are marked for the owner to fill in.
- Sends an optional Telegram status message after every watch check, including checks with no new mail. Messages report counts/actions only; they do not include sender addresses, subjects, email bodies, or draft text.

## Setup

The project uses Python 3.11 and a project virtual environment. Install dependencies with:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Gmail OAuth files belong in the project root as `credentials.json` and `token.json`. They are local secrets and are ignored by Git. EIRA requests Gmail's `gmail.modify` scope to read mail, apply labels, and create drafts. Google also allows sending under that scope; the code has no send operation.

The local model is `qwen3.5:0.8b`, served by Ollama. Classification and reply decisions remain in Python; email content is sent only to the local model for draft wording.

## Telegram notifications

Create a bot with Telegram's `@BotFather` using `/newbot`, open its chat, and send `/start`. Telegram bots cannot start a chat with a user. Keep the bot token private. The BotFather guide and Bot API are linked in [References](#references).

In the same PowerShell window that will run EIRA, set the token and chat ID. This reads the token from the clipboard without printing it:

```powershell
$env:TELEGRAM_BOT_TOKEN = (Get-Clipboard -Raw).Trim()
$updates = Invoke-RestMethod -Uri "https://api.telegram.org/bot$($env:TELEGRAM_BOT_TOKEN)/getUpdates"
$updates.result[-1].message.chat.id
$env:TELEGRAM_CHAT_ID = Read-Host "Paste the chat ID"
```

Before the first `/start`, `getUpdates` may return no messages. Run the command again after sending `/start`. Environment variables apply only to processes started from that PowerShell window. The token is never stored in the project files.

## Run EIRA

Preview a date range without changing Gmail:

```powershell
.\.venv\Scripts\python.exe -m mail_assistant.app --since 2026-10-13
```

Apply labels and create unsent drafts for that range:

```powershell
.\.venv\Scripts\python.exe -m mail_assistant.app --apply --since 2026-10-13
```

Start five-minute monitoring with Gmail actions and Telegram status messages:

```powershell
.\.venv\Scripts\python.exe -m mail_assistant.app --watch --apply
```

Keep the terminal open. Use **Ctrl+C** in that terminal to stop the watcher. Restart it after code changes so the running process loads the updated code. Processed message IDs and the watch checkpoint are stored locally in `.state/processed.sqlite3` to avoid duplicate work and drafts.

## Project files

- `mail_assistant/app.py`: Gmail preview, apply, and watch workflow.
- `mail_assistant/rules.py`: conservative message classification.
- `mail_assistant/drafting.py` and `model.py`: local draft wording and safety fallback.
- `mail_assistant/gmail.py`: Gmail API adapter.
- `mail_assistant/telegram.py`: aggregate Telegram notifications.
- `mail_assistant/store.py`: local duplicate-prevention and checkpoint database.
- `samples/evaluation_cases.json` and `mail_assistant/evaluate.py`: synthetic evaluation data and runner.
- `tests/`: policy and Gmail parsing tests.

## Current limits

The current synthetic evaluation passes 13/13 cases and the unit suite passes 7/7 tests. These checks do not establish reliability on all real mail. The live rules remain conservative, and messages processed before a rule change are not automatically reprocessed. Review labels and drafts in Gmail before relying on them.

Telegram watch notifications have been confirmed working, including the no-new-mail status. A successful no-mail check says that EIRA checked Gmail and found nothing new to process.

## Development checks

Run the policy and Gmail parsing unit tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Run the synthetic local-model evaluation:

```powershell
.\.venv\Scripts\python.exe -m mail_assistant.evaluate
```

## References

- [Gmail API Python quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python)
- [Gmail API OAuth scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [Gmail API drafts](https://developers.google.com/workspace/gmail/api/guides/drafts)
- [Gmail API labels](https://developers.google.com/workspace/gmail/api/guides/labels)
- [Telegram BotFather guide](https://core.telegram.org/bots/features#botfather)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Ollama Qwen 3.5 model](https://ollama.com/library/qwen3.5)
