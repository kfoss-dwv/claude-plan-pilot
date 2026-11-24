# shop (eval fixture)

A tiny order service used by claude-plan-pilot's eval. `POST /orders/quote` prices a cart:
line totals, coupon, tax, shipping. Run the tests with `python3 -m unittest`.
