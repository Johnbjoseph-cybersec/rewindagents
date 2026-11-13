# coupons.py (to be written)

`apply_coupon(cents, code)` returns the amount after the coupon, in whole cents:

- `SAVE10`: 10% off, rounded half up to whole cents (use `cart.apply_discount`);
- `FLAT500`: 500 cents off, never below 0;
- codes are case-insensitive and surrounding spaces are ignored;
- any other code raises `ValueError`.
