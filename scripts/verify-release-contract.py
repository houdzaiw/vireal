"""Validate public release responses without credentials or external writes.

This checks observable contracts, not merchant approval, media rights, deployment
configuration or genuine payment/generation acceptance. Never print response data.
"""

import argparse
import json
import re
import sys
from typing import Any

PACKAGES = {"coins_100": (100, 599), "coins_220": (220, 1199), "coins_500": (500, 2499)}


class ContractError(ValueError):
    """Only fixed, non-sensitive diagnostics may be shown to the operator."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def reject_private_fields(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = {"prompt", "negative_prompt", "model", "object_key", "provider"}
        require(not forbidden.intersection(value), "Catalog exposes internal fields")
        for item in value.values():
            reject_private_fields(item)
    elif isinstance(value, list):
        for item in value:
            reject_private_fields(item)


def validate_catalog(data: Any, mode: str) -> None:
    require(isinstance(data, dict), "Catalog must be an object")
    reject_private_fields(data)
    categories = data.get("categories")
    require(isinstance(categories, list), "Catalog categories must be a list")
    effects = []
    for category in categories:
        require(isinstance(category, dict), "Invalid catalog category")
        items = category.get("effects")
        require(isinstance(items, list), "Catalog effects must be a list")
        effects.extend(items)
    require(len(effects) == 2, "Selected launch must expose exactly two effects")
    require(all(isinstance(effect, dict) for effect in effects), "Invalid effect")
    require(
        {effect.get("slug") for effect in effects} == {"dance-1", "romance-1"},
        "Catalog does not match the selected launch effects",
    )
    for effect in effects:
        expected_inputs = 1 if effect["slug"] == "dance-1" else 2
        require(effect.get("input_image_count") == expected_inputs, "Wrong input count")
        require(bool(effect.get("title_en")), "Effect needs an English title")
        variants = effect.get("variants")
        require(
            isinstance(variants, list) and len(variants) == 2, "Missing 5/10s variants"
        )
        require(all(isinstance(item, dict) for item in variants), "Invalid variant")
        require(
            {item.get("duration_seconds") for item in variants} == {5, 10},
            "Only the 5/10s launch combinations may be exposed",
        )
        for variant in variants:
            cost = variant.get("coin_cost")
            require(
                type(cost) is int and cost > 0, "Launch variants must have coin prices"
            )
        if mode == "public":
            for field in ("poster_url", "preview_video_url"):
                url = effect.get(field)
                require(
                    isinstance(url, str)
                    and re.fullmatch(r"/api/v1/app/media-assets/[0-9a-f-]{36}", url)
                    is not None,
                    "Public launch requires both managed covers and previews",
                )


def validate_commerce(data: Any, mode: str) -> None:
    require(isinstance(data, dict), "PayPal configuration must be an object")
    require(data.get("environment") == "live", "Production must use Live PayPal")
    require(data.get("global_real_limit") == 30, "Daily site limit must be 30")
    remaining = data.get("global_real_remaining")
    require(
        type(remaining) is int and 0 <= remaining <= 30, "Invalid remaining capacity"
    )
    require(isinstance(data.get("resets_at"), str), "Missing UTC capacity reset time")
    require(
        data.get("support_email") == "li522903183@gmail.com", "Wrong support contact"
    )
    products = data.get("products")
    require(
        isinstance(products, list) and len(products) == 3,
        "Exactly three packages required",
    )
    require(
        all(isinstance(item, dict) for item in products), "Invalid recharge package"
    )
    require(
        {item.get("product_id") for item in products} == set(PACKAGES), "Wrong packages"
    )
    for item in products:
        coins, cents = PACKAGES[item["product_id"]]
        require(
            type(item.get("coins")) is int
            and type(item.get("amount")) is int
            and item["coins"] == coins
            and item["amount"] == cents
            and item.get("currency") == "USD",
            "Recharge price/credits must match the approved USD package",
        )
    if mode == "closed":
        require(
            data.get("registration_enabled") is False
            and data.get("recharge_enabled") is False,
            "Registration/recharge are not closed for the observed request",
        )
    else:
        country = data.get("country")
        require(
            isinstance(country, str)
            and re.fullmatch(r"[A-Z]{2}", country) is not None
            and country not in {"CN", "XX", "T1"}
            and data.get("region_allowed") is True,
            "Public-opening checks require a genuine eligible edge region",
        )
        require(
            data.get("registration_enabled") is True
            and data.get("recharge_enabled") is True
            and bool(data.get("client_id"))
            and remaining > 0,
            "Public registration/recharge must be open with remaining capacity",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", choices=("catalog", "commerce"))
    parser.add_argument("mode", choices=("closed", "public"))
    args = parser.parse_args()
    try:
        raw = sys.stdin.read(2 * 1024 * 1024 + 1)
        require(len(raw) <= 2 * 1024 * 1024, "Release response is too large")
        data = json.loads(raw)
        validator = (
            validate_catalog if args.contract == "catalog" else validate_commerce
        )
        validator(data, args.mode)
    except ContractError as exc:
        print(f"Release {args.contract} contract failed: {exc}", file=sys.stderr)
        return 1
    except (ValueError, TypeError, KeyError, RecursionError):
        # Avoid echoing malformed responses, secret fields or provider payloads.
        print(
            f"Release {args.contract} contract failed; inspect it privately",
            file=sys.stderr,
        )
        return 1
    print(f"Release {args.contract} observable contract passed ({args.mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
