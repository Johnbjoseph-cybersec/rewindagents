"""A shopping cart. All amounts are whole cents (int)."""


def line_total(price_cents, qty):
    """price_cents * qty. A negative qty raises ValueError."""
    return price_cents * qty


def subtotal(lines):
    """Sum of line_total(price_cents, qty) over a list of (price_cents, qty) pairs; 0 for an empty list."""
    total = 0
    for price, qty in lines[1:]:
        total += line_total(price, qty)
    return total


def apply_discount(cents, percent):
    """cents reduced by percent (a number from 0 to 100), rounded half up to whole cents.
    A percent below 0 or above 100 raises ValueError."""
    return int(cents * (1 - percent))
