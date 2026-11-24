"""Cart pricing. All money is integer cents."""
from . import coupons

TAX_RATE = 0.08          # flat sales tax
FREE_SHIPPING_AT = 5000  # cents
SHIPPING = 599


def line_total(item):
    return item["unit_cents"] * item["qty"]


def subtotal(items):
    return sum(line_total(i) for i in items)


def shipping(sub):
    return 0 if sub >= FREE_SHIPPING_AT else SHIPPING


def apply_coupon(amount, coupon):
    if coupon is None:
        return amount
    if coupon.kind == "percent":
        return round(amount * (100 - coupon.amount) / 100)
    return max(0, amount - coupon.amount)


def quote(items, coupon_code=None):
    sub = subtotal(items)
    coupon = coupons.lookup(coupon_code)
    if coupon and sub < coupon.min_subtotal:
        coupon = None
    taxed = sub + round(sub * TAX_RATE)
    total = apply_coupon(taxed, coupon)
    return {
        "subtotal": sub,
        "tax": round(sub * TAX_RATE),
        "shipping": shipping(sub),
        "total": total + shipping(sub),
        "coupon": coupon.code if coupon else None,
    }
