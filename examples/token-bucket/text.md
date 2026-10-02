`examples/token_bucket.py` limits requests with a token bucket. Each request costs one token, and a request that finds no token gets a 429 reply.

The bucket lets a client send a short burst, but it holds the long-term rate to a fixed value. The size of the bucket sets the burst (`capacity`, default 20). The speed at which tokens come back sets the rate (`refill_rate`, default 5.0 tokens each second).

The code has no timer. It calculates the new tokens only when a request arrives:

1. `handle` asks the bucket to allow the request.
2. The bucket adds the tokens that it earned: the time since the last call, multiplied by the rate. It never holds more than 20.
3. If the bucket holds 1 token or more, it takes one token and `handle` passes the request to the handler.
4. If not, the bucket takes nothing. `handle` returns 429 with a `Retry-After` header, which gives the seconds until one token is available.

**Example.** Tested with a fake clock and the default values:

At 0 seconds, the bucket is full and 25 requests arrive. The bucket allows 20 and rejects 5, each with `Retry-After: 0.2`. At 0.2 seconds, the bucket allows one request and rejects the next. After one more second with no requests, the bucket holds 5 tokens. After a long pause, it holds 20 again, not more.

**Limits.**

- Tested: a request with a `cost` larger than the capacity can never pass, but `retry_after` gives it a finite time.
- Tested: with a rate of 0, `retry_after` raises `ZeroDivisionError`.
- Inferred: the bucket has no lock, so two threads can use the same token.
- Inferred: the tokens are in the memory of one process. A restart gives a full bucket, and each process has its own bucket.
- `handle` uses the one bucket that the caller gives. If each client needs its own limit, the caller must keep one bucket for each client.
