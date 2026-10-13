import base64
import unittest

from mail_assistant.gmail import MailMessage, create_reply_draft, parse_gmail_message


class GmailParsingTests(unittest.TestCase):
    def test_parses_plain_text_and_reply_headers(self):
        encoded = base64.urlsafe_b64encode(b"Please confirm the shipment status.").decode().rstrip("=")
        parsed = parse_gmail_message(
            {
                "id": "m-1",
                "threadId": "t-1",
                "internalDate": "1234",
                "payload": {
                    "mimeType": "text/plain",
                    "headers": [
                        {"name": "From", "value": "Buyer <buyer@example.com>"},
                        {"name": "Reply-To", "value": "replies@example.com"},
                        {"name": "Subject", "value": "Tender status"},
                        {"name": "Message-ID", "value": "<message-1@example.com>"},
                    ],
                    "body": {"data": encoded},
                },
            }
        )
        self.assertEqual(parsed.body, "Please confirm the shipment status.")
        self.assertEqual(parsed.reply_to, "replies@example.com")
        self.assertEqual(parsed.thread_id, "t-1")


class GmailDraftTests(unittest.TestCase):
    def test_creates_reply_draft_in_existing_thread(self):
        calls = {}

        class Request:
            def execute(self):
                return {"id": "draft-1"}

        class Drafts:
            def create(self, *, userId, body):
                calls["userId"] = userId
                calls["body"] = body
                return Request()

        class Users:
            def drafts(self):
                return Drafts()

        class Service:
            def users(self):
                return Users()

        message = MailMessage(
            message_id="m-1",
            thread_id="t-1",
            sender="Buyer <buyer@example.com>",
            reply_to="replies@example.com",
            subject="Tender status",
            body="Has it shipped?",
            message_id_header="<message-1@example.com>",
            references="",
            internal_date_ms=0,
        )
        draft_id = create_reply_draft(Service(), message, "[PLEASE CONFIRM: shipment status]")
        self.assertEqual(draft_id, "draft-1")
        self.assertEqual(calls["userId"], "me")
        self.assertEqual(calls["body"]["message"]["threadId"], "t-1")
        self.assertIn("raw", calls["body"]["message"])


if __name__ == "__main__":
    unittest.main()
