---
type: llm
weight: 2
---

The reply explains a token bucket rate limiter whose code was given to the writer.

PASS only if all of these are true:
- It says that a request is allowed only when the bucket holds enough tokens, and that an allowed request takes a token.
- It gives the bucket size of 20 tokens and the refill rate of 5 tokens each second.
- It says that a rejected request gets status 429 and a Retry-After value.

FAIL if one of these is missing, or if the reply states a number or a behaviour that contradicts the three points above.
