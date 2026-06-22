import asyncio
import secrets

import httpx


class Throttle:
    """Manages concurrency and retries for HTTP requests with 429 backoff."""

    def __init__(self, concurrency: int):
        """Initialize throttle with max concurrent requests.

        Args:
            concurrency: Maximum number of concurrent requests to allow.
        """
        self.semaphore = asyncio.Semaphore(concurrency)

    async def run(self, coro_factory):
        """Run a coroutine factory under semaphore control with 429 retry logic.

        Args:
            coro_factory: An async callable that returns a coroutine. Called fresh
                         on each attempt so retries get a new coroutine instance.

        Returns:
            The result of coro_factory() if successful.

        Raises:
            httpx.HTTPStatusError: The last exception if all retries exhausted.
            Other exceptions are propagated immediately without retry.
        """
        max_attempts = 4
        base_delay = 0.01
        jitter_ms = 10

        async with self.semaphore:
            last_error = None

            for attempt in range(max_attempts):
                try:
                    coro = coro_factory()
                    return await coro
                except httpx.HTTPStatusError as e:
                    # Only retry on 429 (Too Many Requests)
                    if e.response.status_code != 429:
                        raise
                    last_error = e
                    # Don't sleep after the last attempt
                    if attempt < max_attempts - 1:
                        # Exponential backoff with jitter
                        delay = base_delay * (2 ** attempt)
                        jitter = secrets.randbelow(jitter_ms) / 1000
                        await asyncio.sleep(delay + jitter)

            # All attempts exhausted, re-raise last 429 error
            raise last_error
