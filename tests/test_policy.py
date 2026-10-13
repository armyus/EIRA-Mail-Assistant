import unittest

from mail_assistant.policy import REVIEW_LABEL, validate_suggestion


class ValidateSuggestionTests(unittest.TestCase):
    def test_allows_multiple_known_labels_and_a_draft(self):
        decision = validate_suggestion(
            {
                "labels": ["Action needed", "Urgent or time-sensitive"],
                "needs_reply": True,
                "confidence": 0.9,
                "draft_body": "[PLEASE CONFIRM: your decision]",
            }
        )
        self.assertFalse(decision.requires_review)
        self.assertIn("Needs a reply", decision.labels)
        self.assertIn("Urgent or time-sensitive", decision.labels)

    def test_low_confidence_fails_closed(self):
        decision = validate_suggestion(
            {
                "labels": ["Informational"],
                "needs_reply": False,
                "confidence": 0.2,
                "draft_body": None,
            }
        )
        self.assertTrue(decision.requires_review)
        self.assertEqual(decision.labels, (REVIEW_LABEL,))
        self.assertIsNone(decision.draft_body)

    def test_unknown_label_fails_closed(self):
        decision = validate_suggestion(
            {
                "labels": ["Looks harmless"],
                "needs_reply": False,
                "confidence": 0.99,
                "draft_body": None,
            }
        )
        self.assertTrue(decision.requires_review)
        self.assertEqual(decision.labels, (REVIEW_LABEL,))

    def test_reply_without_draft_fails_closed(self):
        decision = validate_suggestion(
            {
                "labels": ["Needs a reply"],
                "needs_reply": True,
                "confidence": 0.9,
                "draft_body": None,
            }
        )
        self.assertTrue(decision.requires_review)
        self.assertIsNone(decision.draft_body)

    def test_non_reply_message_cannot_smuggle_in_a_draft(self):
        decision = validate_suggestion(
            {
                "labels": ["Informational"],
                "needs_reply": False,
                "confidence": 0.9,
                "draft_body": "I approved it.",
            }
        )
        self.assertTrue(decision.requires_review)
        self.assertIsNone(decision.draft_body)


if __name__ == "__main__":
    unittest.main()
