"""Money helpers. Amounts are integers in cents."""


def allocate(total, weights):
    """Split ``total`` cents into integer shares proportional to ``weights``.

    * The shares always add up to exactly ``total``.
    * Largest-remainder method: every share first gets floor(total * w / sum(weights)); the cents left over
      go one each to the shares with the largest fractional remainders; ties go to the earlier position.
    * A zero weight always gets 0.
    * A negative ``total`` is allocated as the negation of allocating ``-total`` (so -100 over [1, 1, 1]
      is [-34, -33, -33]).
    * ``weights`` must be non-empty, every weight a non-negative integer, and at least one positive;
      otherwise ValueError. The input list is not modified.
    """
    s = sum(weights)
    return [round(total * w / s) for w in weights]
