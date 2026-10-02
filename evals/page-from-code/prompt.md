---
description: A request for an interactive page about code that is in the prompt, saved at a path that the user names.
tags: [page]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill]
---

Build an interactive page that explains this rate limiter. I want to change the size of a burst and see how many requests pass. Save it as rate-limiter.html in the current folder.

```python
"""A token bucket rate limiter.

This file is the subject of the examples in this folder: the same code, explained four ways.
"""

import time


class TokenBucket:
    """Allow a burst of up to `capacity` requests, then `refill_rate` requests each second."""

    def __init__(self, capacity=20, refill_rate=5.0, clock=time.monotonic):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = float(capacity)  # the bucket starts full
        self.clock = clock
        self.updated = clock()

    def _refill(self):
        """Add the tokens earned since the last call. The bucket never holds more than `capacity`."""
        now = self.clock()
        earned = (now - self.updated) * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + earned)
        self.updated = now

    def allow(self, cost=1):
        """Take `cost` tokens and return True, or return False if the bucket does not hold enough."""
        self._refill()
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False

    def retry_after(self, cost=1):
        """Seconds until the bucket holds `cost` tokens."""
        self._refill()
        return max(0.0, (cost - self.tokens) / self.refill_rate)


def handle(bucket, request, handler):
    """Answer one request: pass it to the handler, or reject it with 429 and a Retry-After header."""
    if bucket.allow():
        return handler(request)
    wait = bucket.retry_after()
    return 429, {"Retry-After": "%.1f" % wait}, "Too Many Requests"
```
