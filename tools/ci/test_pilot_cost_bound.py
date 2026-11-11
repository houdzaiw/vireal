import unittest
from decimal import Decimal

from pilot_cost_bound import (
    REQUIRED,
    CostBound,
    R2Usage,
    Unproven,
    assess,
    r2_cycle_cost,
    r2_phase_costs,
)


class PilotCostBounds(unittest.TestCase):
    def test_synthetic_usage_with_free_tier(self):
        self.assertEqual(r2_cycle_cost(R2Usage(".25", 128, 2048), free_tier=True), 0)

    def test_billable_units_round_up(self):
        self.assertEqual(
            r2_cycle_cost(R2Usage("10.1", 1000001, 10000001), free_tier=True),
            Decimal("4.875"),
        )

    def test_no_double_rounding_between_phases(self):
        zero = R2Usage("0", 0, 0)
        tiny = R2Usage(".001", 1, 1)
        self.assertEqual(
            r2_phase_costs([(zero, tiny, tiny, False)]), (Decimal("4.875"), 0)
        )

    def test_new_cycle_has_separate_rounding(self):
        z, tiny = R2Usage("0", 0, 0), R2Usage(".001", 0, 0)
        self.assertEqual(
            r2_phase_costs([(z, tiny, z, False), (z, tiny, z, False)])[0],
            Decimal(".030"),
        )

    def test_missing_cycles_rejected(self):
        with self.assertRaises(Unproven):
            r2_phase_costs([])

    def test_invalid_quantities_rejected(self):
        for value in ["NaN", "Infinity", "-1", 0.1]:
            with self.subTest(value=value), self.assertRaises(Unproven):
                R2Usage(value, 0, 0)
        for value in [-1, True, 1.1]:
            with self.subTest(value=value), self.assertRaises(Unproven):
                R2Usage("0", value, 0)

    def evaluate(self, bounds=None, **kwargs):
        values = {
            "next_order_usd": "0",
            "paid_balance_liability_usd": "0",
            "ongoing_service_liability_usd": "0",
            "liability_evidence": "synthetic only",
        }
        values.update(kwargs)
        if bounds is None:
            bounds = {s: CostBound("0", "0", "synthetic only", True) for s in REQUIRED}
        return assess(bounds, **values)

    def test_missing_sources_fail_closed(self):
        self.assertFalse(self.evaluate({})["arithmetic_eligible"])

    def test_missing_long_tail_is_not_zero(self):
        r = self.evaluate(paid_balance_liability_usd=None)
        self.assertFalse(r["arithmetic_eligible"])

    def test_invalidated_evidence_blocks(self):
        bounds = {s: CostBound("0", "0", "synthetic only", True) for s in REQUIRED}
        bounds["r2"] = CostBound("0", "0", "old", False)
        self.assertFalse(self.evaluate(bounds)["arithmetic_eligible"])

    def test_exact_120_rejected(self):
        self.assertFalse(self.evaluate(next_order_usd="120")["arithmetic_eligible"])

    def test_future_liabilities_count_in_closing(self):
        self.assertFalse(
            self.evaluate(
                paid_balance_liability_usd="10", ongoing_service_liability_usd="20.01"
            )["arithmetic_eligible"]
        )

    def test_eligible_arithmetic_does_not_authorize_promotion(self):
        r = self.evaluate(next_order_usd="119.99", paid_balance_liability_usd="30")
        self.assertTrue(r["arithmetic_eligible"])
        self.assertFalse(r["promotion_authorized"])


if __name__ == "__main__":
    unittest.main()
