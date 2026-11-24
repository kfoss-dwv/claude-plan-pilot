"""HTTP handlers (framework-free for the fixture: a handler takes a dict, returns (status, body))."""
from . import pricing


def post_quote(body):
    items = body.get("items") or []
    if not items:
        return 400, {"error": "cart is empty"}
    for i in items:
        if i.get("qty", 0) <= 0:
            return 400, {"error": f"bad qty for {i.get('sku')}"}
    return 200, pricing.quote(items, body.get("coupon"))
