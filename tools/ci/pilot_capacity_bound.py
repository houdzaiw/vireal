"""Exact offline capacity arithmetic. No provider I/O or runtime authorization.

All inputs must be independently bounded. Retention minimums never imply a
successful deletion, and a one-attempt executable is not a global retry limit.
"""

from dataclasses import dataclass
from decimal import Decimal

from pilot_cost_bound import Unproven, count, quantity, units


def positive_count(value: int) -> int:
    count(value)
    if value == 0:
        raise Unproven("A positive bound is required")
    return value


def backup_storage_bound(
    *,
    business_hours: str,
    closing_hours: str | None,
    interval_minutes: int,
    streams: int,
    extra_captures: int,
    attempts_per_capture: int | None,
    ciphertext_cap_bytes: int,
    manifest_cap_bytes: int,
) -> dict:
    if closing_hours is None:
        raise Unproven("Closing/capture horizon is unbounded")
    if attempts_per_capture is None:
        raise Unproven("Failed/unknown attempts have no global bound")
    hours = quantity(business_hours) + quantity(closing_hours)
    cadence = positive_count(interval_minutes)
    scheduled = int(units(hours * 60 / cadence)) + 1
    captures = scheduled * positive_count(streams) + count(extra_captures)
    attempts = captures * positive_count(attempts_per_capture)
    per_attempt = positive_count(ciphertext_cap_bytes) + count(manifest_cap_bytes)
    return {
        "scheduled_per_stream_including_endpoints": scheduled,
        "logical_captures": captures,
        "maximum_attempts": attempts,
        "retained_bytes_bound": attempts * per_attempt,
        "deletion_credit_bytes": 0,
        "runtime_enforcement_verified": False,
        "promotion_authorized": False,
    }


def ciphertext_budget(
    *,
    available_bytes: int | None,
    reserve_bytes: int,
    other_future_bytes: int | None,
    attempts: int,
    manifest_cap_bytes: int,
) -> int:
    if available_bytes is None or other_future_bytes is None:
        raise Unproven("Current free capacity or other consumers are unbounded")
    usable = count(available_bytes) - count(reserve_bytes) - count(other_future_bytes)
    budget = usable // positive_count(attempts) - count(manifest_cap_bytes)
    return max(0, budget)


def neon_compute_bound(*, maximum_cu: str, hours: str | None) -> Decimal:
    if hours is None:
        raise Unproven("Compute service duration is unbounded")
    maximum = quantity(maximum_cu)
    if maximum == 0:
        raise Unproven("Maximum compute allocation must be explicit")
    return maximum * quantity(hours)


@dataclass(frozen=True)
class PoolGroup:
    processes_per_copy: int
    pool_size: int
    overflow: int
    concurrent_copies: int

    def maximum(self) -> int:
        return (
            positive_count(self.processes_per_copy)
            * (positive_count(self.pool_size) + count(self.overflow))
            * count(self.concurrent_copies)
        )


def connection_bound(groups: list[PoolGroup], *, other_connections: int | None) -> int:
    if not groups or other_connections is None:
        raise Unproven(
            "All pool generations and non-application consumers are required"
        )
    return sum(group.maximum() for group in groups) + count(other_connections)
