from dataclasses import dataclass


@dataclass(frozen=True)
class Coupon:
    code: str
    kind: str          # "percent" | "fixed"
    amount: int        # percent points, or cents for "fixed"
    min_subtotal: int = 0


COUPONS = {
    "SAVE10": Coupon("SAVE10", "percent", 10),
    "FIVEOFF": Coupon("FIVEOFF", "fixed", 500, min_subtotal=2500),
}


def lookup(code):
    return COUPONS.get((code or "").strip().upper())
