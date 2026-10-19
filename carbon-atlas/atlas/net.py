"""The HTTP client.

One client for the whole run. It owns the rate limit and the tries, so a
collector module holds no network logic. REFERENCE.md section 6.

The rate limit comes from `sources/sources.json`. energy-charts publishes 2
requests each minute, so the client waits 30 seconds between two requests to
that source. The limit is per source, and not per process.

TLS: httpx verifies with the certifi bundle. A probe on 2026-09-17 confirmed
that this works on the Wirtek laptop for `api.energy-charts.info`. On a machine
where a proxy breaks the chain, set `ATLAS_CA_BUNDLE` to the CA file of the
proxy. The program never turns the verification off.
"""

from __future__ import annotations

import time
from collections import defaultdict

import httpx

from . import config, log
from .model import FetchError

# The status codes that make another try of the same request.
_RETRY_STATUS = {408, 429, 500, 502, 503, 504}


class Http:
    def __init__(self, tries: int = config.HTTP_TRIES) -> None:
        verify = config.CA_BUNDLE or True
        self._client = httpx.Client(
            timeout=config.HTTP_TIMEOUT_SECONDS,
            verify=verify,
            follow_redirects=True,
            headers={"User-Agent": "carbon-atlas/0.1 (Wirtek, internal research)"},
        )
        self._tries = tries
        self._last_call: dict[str, float] = defaultdict(float)
        self._log = log.get("atlas.net")

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Http":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def _wait_for_rate(self, source_id: str) -> None:
        per_minute = config.requests_per_minute(source_id)
        if per_minute <= 0:
            return
        gap = 60.0 / per_minute
        since = time.monotonic() - self._last_call[source_id]
        if since < gap:
            time.sleep(gap - since)

    def get(
        self,
        source_id: str,
        url: str,
        params: dict | None = None,
        tries: int | None = None,
    ) -> tuple[int, bytes]:
        """One GET request, with the rate limit and the tries.

        It returns (status, bytes). It raises `FetchError` after the last try.

        `tries` makes the count smaller for one call. The runner sets it to 1
        for a window that it can split, because a split is the better answer to
        a server error. A try costs 30 seconds of rate limit, and a split makes
        a smaller question that the server can answer.
        """
        count = self._tries if tries is None else max(1, tries)
        last_error = "no request ran"
        last_status: int | None = None

        for attempt in range(1, count + 1):
            self._wait_for_rate(source_id)
            self._last_call[source_id] = time.monotonic()
            try:
                response = self._client.get(url, params=params)
            except httpx.HTTPError as error:
                last_error = f"{type(error).__name__}: {error}"
                last_status = None
            else:
                last_status = response.status_code
                if response.status_code == 200:
                    return response.status_code, response.content
                last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                if response.status_code not in _RETRY_STATUS:
                    raise FetchError(last_error, response.status_code)
                pause = _retry_after(response)
                if pause:
                    self._log.info("HTTP %s. The client waits %s s.", last_status, pause)
                    time.sleep(pause)

            if attempt < count:
                self._log.warning(
                    "try %d of %d failed for %s: %s", attempt, count, url, last_error
                )
                time.sleep(min(60, 5 * attempt))

        raise FetchError(last_error, last_status)


def _retry_after(response: httpx.Response) -> float:
    """The `Retry-After` header in seconds. 0 when the header is absent."""
    value = response.headers.get("Retry-After")
    if not value:
        return 0.0
    try:
        return max(0.0, min(300.0, float(value)))
    except ValueError:
        return 0.0
