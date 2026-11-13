"""A small least-recently-used cache whose entries expire."""
import time
from collections import OrderedDict

_MISSING = object()


class TTLCache:
    def __init__(self, capacity, ttl, clock=time.monotonic):
        if capacity < 1 or not ttl > 0:
            raise ValueError("capacity >= 1 and ttl > 0 required")
        self.capacity, self.ttl, self.clock = capacity, ttl, clock
        self._data = OrderedDict()

    def _live(self, key, now):
        item = self._data.get(key)
        return item is not None and now < item[1] + self.ttl

    def set(self, key, value):
        now = self.clock()
        self._data[key] = (value, now)
        self._data.move_to_end(key)
        if len(self._data) > self.capacity:
            for k in [k for k in self._data if not self._live(k, now)]:
                del self._data[k]
        while len(self._data) > self.capacity:
            self._data.popitem(last=False)

    def get(self, key, default=None):
        now = self.clock()
        if key not in self._data:
            return default
        if not self._live(key, now):
            del self._data[key]
            return default
        self._data.move_to_end(key)
        return self._data[key][0]

    def get_or_set(self, key, factory):
        v = self.get(key, _MISSING)
        if v is _MISSING:
            v = factory()
            self.set(key, v)
        return v

    def __len__(self):
        now = self.clock()
        return sum(1 for k in self._data if self._live(k, now))

    def __contains__(self, key):
        return self._live(key, self.clock())
