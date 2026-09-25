"""Money is stored internally as integer cents to avoid float rounding
errors. These helpers are the only place conversion to/from the API's
string representation ("1250.00") should happen.
"""
from decimal import Decimal, ROUND_HALF_UP


def to_cents(amount) -> int:
    """Convert a request amount (float, int, str, Decimal) to integer cents.

    Uses Decimal so that values like 0.10 don't pick up float noise before
    rounding. Rejects anything that isn't a whole number of cents once
    rounded to 2 decimal places is fine (we round, we don't truncate) --
    but we still round HALF_UP at the cent boundary, matching normal
    currency rounding rules.
    """
    d = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(d * 100)


def cents_to_str(cents: int) -> str:
    """Format integer cents as a two-decimal money string, e.g. 75000 -> '750.00'."""
    d = Decimal(cents) / 100
    return f"{d:.2f}"