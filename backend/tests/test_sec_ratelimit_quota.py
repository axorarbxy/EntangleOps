from __future__ import annotations
from security.ratelimit import TokenBucketLimiter

def test_token_bucket_capacity():
    limiter=TokenBucketLimiter(2)
    assert limiter.consume("k") and limiter.consume("k") and not limiter.consume("k")
