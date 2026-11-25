import importlib.util
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("check_budget", Path(__file__).with_name("check_budget.py"))
budget = importlib.util.module_from_spec(spec)
spec.loader.exec_module(budget)


class BudgetGuardTest(unittest.TestCase):
    def setUp(self):
        self.bundle = {"bundleId": "medium_3_1", "price": 24, "isActive": True,
                       "ramSizeInGb": 4, "cpuCount": 2}
        self.plan = {"accountPlanType": "FREE", "accountPlanStatus": "ACTIVE",
                     "accountPlanRemainingCredits": {"amount": "99.999985", "unit": "USD"},
                     "accountPlanExpirationDate": "2027-03-11T13:16:42.885Z"}
        self.start = datetime(2026, 11, 23, tzinfo=timezone.utc)

    def assess(self, **kwargs):
        return budget.assess(self.bundle, self.plan, start=self.start,
                             days=kwargs.pop("days", Decimal("108")), **kwargs)

    def test_fits_credit_window_and_keeps_reserve(self):
        result = self.assess(eligible=True)
        self.assertEqual(result["status"], "BUDGET_PREFLIGHT_PASS")
        self.assertEqual(result["compute_estimate_usd"], "85.22")
        self.assertEqual(result["contingency_usd"], "10.00")

    def test_expiry_blocks_stated_110_days(self):
        result = self.assess(days=Decimal("110"), eligible=True)
        self.assertEqual(result["status"], "BUDGET_PREFLIGHT_BLOCKED")
        self.assertIn("expiry", " ".join(result["blockers"]))

    def test_unknown_eligibility_is_not_success(self):
        self.assertEqual(self.assess()["status"], "BUDGET_PREFLIGHT_BLOCKED")

    def test_no_8gb_upgrade_to_fit_resource_problem(self):
        self.bundle.update(ramSizeInGb=8, price=44)
        result = self.assess(eligible=True)
        self.assertGreaterEqual(len(result["blockers"]), 2)

    def test_other_spending_consumes_headroom(self):
        result = self.assess(eligible=True, other_cost=Decimal("10"))
        self.assertIn("contingency", " ".join(result["blockers"]))

    def test_nonfinite_credit_input_rejected(self):
        self.plan["accountPlanRemainingCredits"]["amount"] = "NaN"
        with self.assertRaises(ValueError):
            self.assess(eligible=True)

    def test_cannot_remove_contingency_or_expand_allowance(self):
        with self.assertRaises(ValueError):
            self.assess(eligible=True, reserve=Decimal("0"))
        with self.assertRaises(ValueError):
            self.assess(eligible=True, initial_allowance=Decimal("200"))

    def test_budget_alerts_are_absolute_and_precredit(self):
        result = budget.budget_template("123456789012", "owner@example.test", self.start, self.start)
        self.assertFalse(result["Budget"]["CostTypes"]["IncludeCredit"])
        self.assertEqual([row["Notification"]["Threshold"] for row in result["NotificationsWithSubscribers"]], [25, 50, 75, 90])
        self.assertTrue(all(row["Notification"]["ThresholdType"] == "ABSOLUTE_VALUE" for row in result["NotificationsWithSubscribers"]))


if __name__ == "__main__":
    unittest.main()
