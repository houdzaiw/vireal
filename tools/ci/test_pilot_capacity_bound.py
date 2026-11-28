import unittest
from decimal import Decimal

from pilot_capacity_bound import (
    PoolGroup,
    backup_storage_bound,
    ciphertext_budget,
    connection_bound,
    neon_compute_bound,
)
from pilot_cost_bound import Unproven


class CapacityBounds(unittest.TestCase):
    def scenario(self, **changes):
        inputs = dict(
            business_hours="72",
            closing_hours="0",
            interval_minutes=45,
            streams=1,
            extra_captures=0,
            attempts_per_capture=1,
            ciphertext_cap_bytes=96 * 1024**2,
            manifest_cap_bytes=4096,
        )
        return backup_storage_bound(**(inputs | changes))

    def test_exact_endpoint_and_fractional_horizon(self):
        self.assertEqual(self.scenario()["logical_captures"], 97)
        self.assertEqual(self.scenario(closing_hours=".01")["logical_captures"], 98)
        self.assertEqual(self.scenario(closing_hours="24")["logical_captures"], 129)
        self.assertEqual(self.scenario(closing_hours="48")["logical_captures"], 161)

    def test_extra_streams_and_unknown_outcomes_consume_capacity(self):
        r = self.scenario(streams=2, extra_captures=3, attempts_per_capture=2)
        self.assertEqual(r["maximum_attempts"], (97 * 2 + 3) * 2)
        self.assertEqual(
            r["retained_bytes_bound"], r["maximum_attempts"] * (96 * 1024**2 + 4096)
        )
        self.assertEqual(r["deletion_credit_bytes"], 0)
        self.assertFalse(r["runtime_enforcement_verified"])
        self.assertFalse(r["promotion_authorized"])

    def test_minimum_retention_does_not_reclaim_space(self):
        r = self.scenario(closing_hours="264")
        self.assertEqual(r["logical_captures"], 449)
        self.assertEqual(r["deletion_credit_bytes"], 0)

    def test_missing_tail_or_global_retry_cap_rejected(self):
        for change in ({"closing_hours": None}, {"attempts_per_capture": None}):
            with self.assertRaises(Unproven):
                self.scenario(**change)

    def test_invalid_and_nonfinite_inputs_rejected(self):
        for change in (
            {"closing_hours": "Infinity"},
            {"business_hours": "NaN"},
            {"interval_minutes": 0},
            {"streams": True},
            {"attempts_per_capture": 0},
            {"extra_captures": -1},
        ):
            with self.subTest(change=change), self.assertRaises(Unproven):
                self.scenario(**change)

    def test_free_capacity_is_not_reduced_by_already_stored_files_again(self):
        self.assertEqual(
            ciphertext_budget(
                available_bytes=1000,
                reserve_bytes=100,
                other_future_bytes=200,
                attempts=2,
                manifest_cap_bytes=50,
            ),
            300,
        )

    def test_unknown_other_consumers_not_zero(self):
        for free, other in ((None, 0), (1000, None)):
            with self.assertRaises(Unproven):
                ciphertext_budget(
                    available_bytes=free,
                    reserve_bytes=0,
                    other_future_bytes=other,
                    attempts=1,
                    manifest_cap_bytes=0,
                )

    def test_ciphertext_budget_boundary_and_no_room(self):
        self.assertEqual(
            ciphertext_budget(
                available_bytes=100,
                reserve_bytes=0,
                other_future_bytes=0,
                attempts=3,
                manifest_cap_bytes=1,
            ),
            32,
        )
        self.assertEqual(
            ciphertext_budget(
                available_bytes=100,
                reserve_bytes=101,
                other_future_bytes=0,
                attempts=1,
                manifest_cap_bytes=1,
            ),
            0,
        )

    def test_per_project_compute_does_not_share_free_allowance(self):
        self.assertEqual(
            neon_compute_bound(maximum_cu=".25", hours="96"), Decimal("24")
        )
        self.assertEqual(neon_compute_bound(maximum_cu="2", hours="72"), Decimal("144"))
        with self.assertRaises(Unproven):
            neon_compute_bound(maximum_cu=".25", hours=None)

    def test_rollout_overlap_and_non_app_connections_are_additive(self):
        old, new = PoolGroup(3, 5, 10, 1), PoolGroup(3, 5, 0, 1)
        self.assertEqual(connection_bound([old, new], other_connections=9), 69)
        self.assertEqual(
            connection_bound([old, PoolGroup(3, 5, 0, 2)], other_connections=9), 84
        )

    def test_unbounded_pool_or_missing_non_app_connections_rejected(self):
        with self.assertRaises(Unproven):
            PoolGroup(3, 5, -1, 1).maximum()
        with self.assertRaises(Unproven):
            connection_bound([PoolGroup(3, 5, 0, 1)], other_connections=None)


if __name__ == "__main__":
    unittest.main()
