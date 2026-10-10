"""Stripe minor-unit display formatting (zero-decimal vs two-decimal)."""

from app.services.stripe_money import ZERO_DECIMAL_CURRENCIES, format_stripe_amount
from app.services.webhook_handlers import _money
from tests.stripe_helpers import store_event


def test_usd_uses_two_fractional_digits():
    assert format_stripe_amount(2000, "usd") == "20.00 USD"
    assert format_stripe_amount(4200, "USD") == "42.00 USD"


def test_jpy_is_zero_decimal():
    assert format_stripe_amount(500, "jpy") == "500 JPY"
    assert format_stripe_amount(1234, "JPY") == "1234 JPY"


def test_krw_is_zero_decimal():
    assert format_stripe_amount(1000, "krw") == "1000 KRW"


def test_null_amount_or_currency():
    assert format_stripe_amount(None, "usd") == "—"
    assert format_stripe_amount(2000, None) == "—"
    assert format_stripe_amount(None, None) == "—"


def test_blank_currency():
    assert format_stripe_amount(100, "   ") == "—"


def test_zero_decimal_set_includes_jpy():
    assert "jpy" in ZERO_DECIMAL_CURRENCIES
    assert "usd" not in ZERO_DECIMAL_CURRENCIES


def test_handler_money_summary_uses_display_formatting(db_session, stripe_integration_id):
    usd = store_event(
        db_session,
        stripe_integration_id,
        event_id="evt_usd_fmt",
        object_id="pi_usd",
    )
    usd.amount = 2500
    usd.currency = "usd"
    jpy = store_event(
        db_session,
        stripe_integration_id,
        event_id="evt_jpy_fmt",
        object_id="pi_jpy",
    )
    jpy.amount = 500
    jpy.currency = "jpy"
    missing = store_event(
        db_session,
        stripe_integration_id,
        event_id="evt_missing_amt",
        object_id="pi_missing",
    )
    missing.amount = None
    missing.currency = "usd"
    db_session.commit()

    assert _money(usd) == "25.00 USD"
    assert _money(jpy) == "500 JPY"
    assert _money(missing) == "amount unavailable"
