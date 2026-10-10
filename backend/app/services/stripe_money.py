"""Stripe amount display helpers.

Stored webhook amounts remain integer minor units (Stripe's smallest currency
unit). Display formatting must respect zero-decimal currencies such as JPY —
never blindly divide by 100.
"""

from __future__ import annotations

# Stripe zero-decimal currencies (amount is already in major units).
# https://docs.stripe.com/currencies#zero-decimal
ZERO_DECIMAL_CURRENCIES = frozenset(
    {
        "bif",
        "clp",
        "djf",
        "gnf",
        "jpy",
        "kmf",
        "krw",
        "mga",
        "pyg",
        "rwf",
        "ugx",
        "vnd",
        "vuv",
        "xaf",
        "xof",
        "xpf",
    }
)


def format_stripe_amount(amount: int | None, currency: str | None) -> str:
    """Format a stored Stripe minor-unit amount for operator-facing text.

    Returns ``—`` when amount or currency is missing. Preserves the integer
    amount for zero-decimal currencies; uses two fractional digits otherwise.
    """
    if amount is None or currency is None:
        return "—"
    code = currency.strip().lower()
    if not code:
        return "—"
    label = code.upper()
    if code in ZERO_DECIMAL_CURRENCIES:
        return f"{amount} {label}"
    major = amount / 100
    return f"{major:.2f} {label}"
