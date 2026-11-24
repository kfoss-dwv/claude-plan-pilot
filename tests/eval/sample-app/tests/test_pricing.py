import unittest

from shop.orders import pricing

CART = [{"sku": "mug", "unit_cents": 1500, "qty": 2}]   # 3000


class Quote(unittest.TestCase):
    def test_no_coupon(self):
        q = pricing.quote(CART)
        self.assertEqual(q["total"], 3000 + 240 + 599)

    def test_percent_coupon(self):
        q = pricing.quote(CART, "SAVE10")
        self.assertEqual(q["coupon"], "SAVE10")
        self.assertLess(q["total"], 3000 + 240 + 599)


if __name__ == "__main__":
    unittest.main()
