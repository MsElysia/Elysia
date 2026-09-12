import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CORE_MODULES = ROOT / "core_modules" / "elysia_core_comprehensive"
sys.path.insert(0, str(CORE_MODULES))

from harvest_engine import StripeClient  # noqa: E402


class _FakeStripeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "available": [{"amount": 1200, "currency": "usd"}],
            "pending": [{"amount": 300, "currency": "usd"}],
            "livemode": False,
        }


def test_stripe_balance_without_key_is_not_configured():
    assert StripeClient().get_balance() == {"status": "not_configured"}


def test_stripe_balance_uses_stripe_api():
    with patch("harvest_engine.requests.get", return_value=_FakeStripeResponse()) as get:
        out = StripeClient("sk_test_123").get_balance()

    assert out["status"] == "ok"
    assert out["available"][0]["amount"] == 1200
    assert out["pending"][0]["amount"] == 300
    get.assert_called_once_with(
        "https://api.stripe.com/v1/balance",
        auth=("sk_test_123", ""),
        timeout=10,
    )
