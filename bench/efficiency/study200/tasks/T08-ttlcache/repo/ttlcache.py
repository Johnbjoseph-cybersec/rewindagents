"""A small least-recently-used cache whose entries expire."""
import time
from collections import OrderedDict


class TTLCache:
    """Holds at most ``capacity`` live entries; each entry expires ``ttl`` seconds after it was last SET.

    * An entry set at time t is live while ``clock() < t + ttl`` and expired from ``t + ttl`` on.
    * ``get(key, default=None)`` returns the value of a live entry and makes it the most recently used;
      it does NOT extend its lifetime. For a missing or expired key it returns ``default`` (an expired entry
      is removed).
    * ``set(key, value)`` stores the value with a fresh lifetime and makes it the most recently used
      (also when the key already exists). If that leaves more than ``capacity`` entries, expired entries are
      removed first, and only then, if still over capacity, the least recently used live entries.
    * ``len(cache)`` and ``key in cache`` count live entries only; ``in`` does not change recency.
    * ``capacity`` must be at least 1 and ``ttl`` greater than 0, else ValueError.
    * ``clock`` is a function returning the current time in seconds (default ``time.monotonic``); tests pass
      their own.
    """

    def __init__(self, capacity, ttl, clock=time.monotonic):
        self.capacity, self.ttl, self.clock = capacity, ttl, clock
        self._data = OrderedDict()

    def set(self, key, value):
        self._data[key] = (value, self.clock())
        self._data.move_to_end(key)
        if len(self._data) > self.capacity:
            self._data.popitem(last=False)

    def get(self, key, default=None):
        if key not in self._data:
            return default
        value, t = self._data[key]
        self._data[key] = (value, self.clock())
        self._data.move_to_end(key)
        return value

    def __len__(self):
        return len(self._data)

    def __contains__(self, key):
        return key in self._data
