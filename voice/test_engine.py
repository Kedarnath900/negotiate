import unittest

from engine import analyze_proposal, load_playbook, validate_playbook


class PlaybookTests(unittest.TestCase):
    def setUp(self):
        self.playbook = load_playbook()

    def proposal(self, **overrides):
        proposal = {
            "supplier": "Test Supplier",
            "category": "Electronics",
            "quoted_price": 10100,
            "target_price": 10000,
            "delivery_days": 18,
            "max_delivery_days": 20,
            "payment_days": 45,
            "min_payment_days": 30,
            "notes": "",
        }
        proposal.update(overrides)
        return proposal

    def test_default_playbook_loads_and_is_valid(self):
        self.assertTrue(self.playbook)
        self.assertEqual(validate_playbook(self.playbook), [])

    def test_accept_uses_playbook_thresholds(self):
        result = analyze_proposal(self.proposal(), self.playbook, None)
        self.assertEqual(result["decision"], "ACCEPT")

    def test_reject_uses_configured_percentage(self):
        playbook = dict(self.playbook)
        playbook["price"] = dict(self.playbook["price"])
        playbook["price"]["reject_above_pct"] = 20
        result = analyze_proposal(
            self.proposal(quoted_price=12500),
            playbook,
            None,
        )
        self.assertEqual(result["decision"], "REJECT")

    def test_custom_delivery_limit_changes_acceptance(self):
        playbook = dict(self.playbook)
        playbook["delivery"] = dict(self.playbook["delivery"])
        playbook["delivery"]["max_days"] = 15
        result = analyze_proposal(
            self.proposal(delivery_days=30, max_delivery_days=15),
            playbook,
            None,
        )
        self.assertEqual(result["decision"], "ESCALATE")

    def test_advance_payment_can_be_allowed_by_playbook(self):
        playbook = dict(self.playbook)
        playbook["payment"] = dict(self.playbook["payment"])
        playbook["payment"]["advance_payment_allowed"] = True
        playbook["risk"] = dict(self.playbook["risk"])
        playbook["risk"]["escalate_if_advance_requested"] = True
        result = analyze_proposal(
            self.proposal(notes="Supplier requests advance payment"),
            playbook,
            None,
        )
        self.assertEqual(result["decision"], "ACCEPT")


if __name__ == "__main__":
    unittest.main()
