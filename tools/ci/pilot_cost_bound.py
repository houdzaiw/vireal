"""Offline cost arithmetic. This tool neither verifies providers nor opens business.

Quantities are account-wide enforced upper bounds, grouped by billing cycle.
The caller must independently establish evidence and running configuration.
"""

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, InvalidOperation


class Unproven(ValueError):
    pass


def quantity(value: str) -> Decimal:
    if not isinstance(value, str):
        raise Unproven("Use exact decimal strings")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise Unproven("Quantity must be a decimal string") from exc
    if not result.is_finite() or result < 0:
        raise Unproven("Quantity must be finite and nonnegative")
    return result


def count(value: int) -> int:
    if type(value) is not int or value < 0:
        raise Unproven("Request count must be a nonnegative integer")
    return value


def units(value: Decimal, size: int = 1) -> Decimal:
    return (max(value, Decimal(0)) / size).to_integral_value(rounding=ROUND_CEILING)


@dataclass(frozen=True)
class R2Usage:
    storage_gb_month: str
    class_a: int
    class_b: int

    def __post_init__(self):
        quantity(self.storage_gb_month)
        count(self.class_a)
        count(self.class_b)

    def plus(self, other: "R2Usage") -> "R2Usage":
        return R2Usage(
            str(quantity(self.storage_gb_month) + quantity(other.storage_gb_month)),
            self.class_a + other.class_a,
            self.class_b + other.class_b,
        )


def r2_cycle_cost(usage: R2Usage, *, free_tier: bool) -> Decimal:
    """Standard only. GB-months must already include all daily peaks/consumers."""
    if type(free_tier) is not bool:
        raise Unproven("Free-tier applicability must be explicit")
    storage_free, a_free, b_free = (
        (10, 1_000_000, 10_000_000) if free_tier else (0, 0, 0)
    )
    return (
        Decimal(".015") * units(quantity(usage.storage_gb_month) - storage_free)
        + Decimal("4.50") * units(Decimal(usage.class_a - a_free), 1_000_000)
        + Decimal(".36") * units(Decimal(usage.class_b - b_free), 1_000_000)
    )


def r2_phase_costs(
    cycles: list[tuple[R2Usage, R2Usage, R2Usage, bool]],
) -> tuple[Decimal, Decimal]:
    """Each tuple: pre-window totals, admission increment, closing increment, free tier.

    Aggregate consumers before calling. Never round each bucket or phase alone.
    Unfinished multipart parts must be covered in the storage/operation bounds.
    """
    if not cycles:
        raise Unproven("Billing-cycle coverage is missing")
    admission = closing = Decimal(0)
    for before, business, tail, free in cycles:
        during = before.plus(business)
        after = during.plus(tail)
        admission += r2_cycle_cost(during, free_tier=free) - r2_cycle_cost(
            before, free_tier=free
        )
        closing += r2_cycle_cost(after, free_tier=free) - r2_cycle_cost(
            during, free_tier=free
        )
    return admission, closing


REQUIRED = frozenset(
    {
        "railway",
        "neon-production",
        "neon-staging",
        "replicate",
        "r2",
        "paypal",
        "clerk",
        "resend",
        "cloudflare",
        "other",
    }
)


@dataclass(frozen=True)
class CostBound:
    admission_usd: str | None
    closing_usd: str | None
    evidence: str | None
    # Confirmed outside this calculator: current bounds cover every consumer,
    # retry, unknown submission and reporting delay for both phases.
    verified: bool = False


def assess(
    bounds: dict[str, CostBound],
    *,
    next_order_usd: str,
    paid_balance_liability_usd: str | None,
    ongoing_service_liability_usd: str | None,
    liability_evidence: str | None,
) -> dict:
    """A missing liability is unknown, never zero. Revenue is not a cost credit.

    Liability inputs are additional, not already included in source closing costs.
    A finite horizon alone does not establish funding for non-expiring balances.
    """
    blockers = []
    admission = closing = Decimal(0)
    for source in sorted(REQUIRED | bounds.keys()):
        bound = bounds.get(source)
        if (
            bound is None
            or not bound.verified
            or not bound.evidence
            or bound.admission_usd is None
            or bound.closing_usd is None
        ):
            blockers.append(source + ": upper bound unproven")
            continue
        admission += quantity(bound.admission_usd)
        closing += quantity(bound.closing_usd)
    if (
        paid_balance_liability_usd is None
        or ongoing_service_liability_usd is None
        or not liability_evidence
    ):
        blockers.append(
            "non-expiring paid balances and ongoing service: funding unproven"
        )
    else:
        closing += quantity(paid_balance_liability_usd) + quantity(
            ongoing_service_liability_usd
        )
    next_order = quantity(next_order_usd)
    if admission + next_order >= 120:
        blockers.append("admission including next order must be strictly below $120")
    if closing > 30:
        blockers.append("closing and future obligations exceed $30")
    if admission + next_order + closing > 150:
        blockers.append("total exceeds $150")
    return {
        "arithmetic_eligible": not blockers,
        "promotion_authorized": False,
        "known_admission_usd": str(admission),
        "known_closing_usd": str(closing),
        "blockers": blockers,
        "qualification": "Known subtotals are not upper bounds while any evidence is missing. "
        "Passing arithmetic still requires runtime, TLS, payment, delivery and owner release acceptance.",
    }
