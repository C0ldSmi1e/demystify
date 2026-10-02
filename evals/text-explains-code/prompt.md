---
description: A request for a Simplified Technical English explanation of code that is in the prompt.
tags: [text]
max_turns: 30
timeout_seconds: 480
allowed_tools: [Read, Glob, Grep, Skill]
---

Explain how this rate limiter decides which requests to reject. Write the explanation in Simplified Technical English.

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
