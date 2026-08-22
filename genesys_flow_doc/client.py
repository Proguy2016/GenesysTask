"""Genesys Cloud REST client -- strictly read-only.

Security posture
----------------
This tool documents a configuration; it must never be able to change one.
That is enforced here rather than left to convention:

* `get()` is the only way to reach the Platform API, and it hard-fails on any
  method other than GET and on any host other than the configured
  `api.<region>`.
* The single non-GET request in the whole package is the OAuth token exchange,
  which RFC 6749 requires to be a POST, and which goes to `login.<region>` --
  never to the API. It is isolated in `_authenticate()` and cannot be reached
  with a caller-supplied URL or body.
* `download()` accepts only HTTPS URLs on a Genesys-owned host, so a
  manipulated API response cannot redirect a fetch to an arbitrary server.
* Credentials live in memory for the life of the process, are sent only to the
  token endpoint, and are never logged. `_authenticate()` failures report the
  status code and the server's error body, neither of which echoes the secret.

`tests/test_security.py` asserts these properties against the source so a later
change cannot quietly reintroduce a write path.
"""

from __future__ import annotations

import base64
import logging
import re
import time
from typing import Any, Iterator
from urllib.parse import urlparse

import requests

from .config import Settings

log = logging.getLogger(__name__)

RETRY_STATUS = {408, 429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5

#: Hosts a pre-signed configuration URL is allowed to point at.
ALLOWED_DOWNLOAD_HOSTS = re.compile(
    r"^[A-Za-z0-9.-]+\.(mypurecloud\.(com|ie|de|jp|com\.au)|pure\.cloud|"
    r"us-gov-pure\.cloud|amazonaws\.com)$"
)


class GenesysError(RuntimeError):
    def __init__(self, status: int, url: str, body: str):
        self.status = status
        self.url = url
        self.body = body
        super().__init__(f"HTTP {status} for {url}\n{body[:800]}")


class ReadOnlyViolation(RuntimeError):
    """Raised if anything attempts a non-GET request against the API."""


class GenesysClient:
    """Read-only access to the Genesys Cloud Platform API."""

    def __init__(self, settings: Settings, timeout: float = 30.0):
        self.settings = settings
        self.timeout = timeout
        self.session = requests.Session()
        self._token: str | None = None
        self._token_expiry: float = 0.0

    # ---------------------------------------------------------------- auth

    def _authenticate(self) -> None:
        """Client-credentials token exchange -- the only non-GET request made.

        POST is mandated by RFC 6749 for the token endpoint. It targets
        `login.<region>`, carries no caller-supplied data, and returns a bearer
        token that is held in memory only.
        """
        basic = base64.b64encode(
            f"{self.settings.client_id}:{self.settings.client_secret}".encode()
        ).decode()
        url = f"{self.settings.login_base}/oauth/token"
        resp = self.session.post(
            url,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise GenesysError(resp.status_code, url, resp.text)
        payload = resp.json()
        self._token = payload["access_token"]
        # Refresh a minute early so a long run never trips over an expiry.
        self._token_expiry = time.time() + int(payload.get("expires_in", 3600)) - 60
        log.info("Authenticated against %s", self.settings.login_base)

    def _auth_header(self) -> dict[str, str]:
        if self._token is None or time.time() >= self._token_expiry:
            self._authenticate()
        return {"Authorization": f"Bearer {self._token}"}

    # ------------------------------------------------------------ requests

    def _resolve(self, path: str) -> str:
        """Build the request URL and refuse anything off the configured API host."""
        url = path if path.startswith("http") else f"{self.settings.api_base}{path}"
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise ReadOnlyViolation(f"Refusing a non-HTTPS request: {url}")
        if parsed.netloc != f"api.{self.settings.region}":
            raise ReadOnlyViolation(
                f"Refusing a request to {parsed.netloc}; this client only reads from "
                f"api.{self.settings.region}"
            )
        return url

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET an API path (e.g. '/api/v2/flows/{id}'). Returns parsed JSON."""
        url = self._resolve(path)
        resp = None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            headers = self._auth_header()
            resp = self.session.get(url, headers=headers, params=params, timeout=self.timeout)

            if resp.status_code == 401 and attempt < MAX_ATTEMPTS:
                self._token = None          # token rejected -- re-auth once and retry
                continue
            if resp.status_code in RETRY_STATUS and attempt < MAX_ATTEMPTS:
                delay = float(resp.headers.get("Retry-After") or 2 ** attempt)
                log.warning("HTTP %s from %s -- retrying in %.0fs", resp.status_code, url, delay)
                time.sleep(min(delay, 60))
                continue
            if resp.status_code >= 400:
                raise GenesysError(resp.status_code, url, resp.text)
            if not resp.content:
                return None
            return resp.json()

        raise GenesysError(resp.status_code if resp else 0, url, resp.text if resp else "")

    def get_optional(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Same as get(), but returns None on 403/404 instead of raising.

        Documentation generation should never die because the OAuth client
        happens to lack read access to one referenced object.
        """
        try:
            return self.get(path, params)
        except GenesysError as exc:
            if exc.status in (403, 404):
                log.warning("Skipping %s (HTTP %s)", path, exc.status)
                return None
            raise

    def paged(self, path: str, params: dict[str, Any] | None = None,
              page_size: int = 100, max_pages: int = 100) -> Iterator[dict]:
        """Iterate every entity across a paged Genesys collection endpoint."""
        page = 1
        while page <= max_pages:
            merged = dict(params or {})
            merged.update({"pageSize": page_size, "pageNumber": page})
            payload = self.get_optional(path, merged)
            if not payload:
                return
            entities = payload.get("entities") or []
            for entity in entities:
                yield entity
            page_count = payload.get("pageCount")
            if page_count is not None and page >= page_count:
                return
            if len(entities) < page_size:
                return
            page += 1

    def download(self, url: str) -> Any:
        """Fetch a pre-signed configuration URL returned by the API.

        The URL comes from an API response rather than from us, so it is checked
        against an allowlist of Genesys-owned hosts before being requested. No
        credentials are attached -- the URL carries its own signature.
        """
        parsed = urlparse(url)
        if parsed.scheme != "https" or not ALLOWED_DOWNLOAD_HOSTS.match(parsed.netloc):
            raise ReadOnlyViolation(f"Refusing to download from {parsed.netloc or url!r}")
        resp = self.session.get(url, timeout=self.timeout)
        if resp.status_code >= 400:
            raise GenesysError(resp.status_code, url, resp.text)
        return resp.json()
