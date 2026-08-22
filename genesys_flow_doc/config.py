"""Region handling, credential loading and Genesys console URL parsing."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import urlparse

# Genesys Cloud runs the same API surface on every regional domain; the only
# thing that changes is the DNS suffix. Rather than hard-coding a table that
# goes stale every time a region launches, we derive the hosts from the domain.
KNOWN_REGIONS = [
    "mypurecloud.com",       # us-east-1
    "use2.us-gov-pure.cloud",
    "usw2.pure.cloud",
    "cac1.pure.cloud",
    "mypurecloud.ie",        # eu-west-1  <- the org in the task URL
    "euw2.pure.cloud",
    "euc2.pure.cloud",
    "mypurecloud.de",
    "aps1.pure.cloud",
    "apne2.pure.cloud",
    "apne3.pure.cloud",
    "mypurecloud.jp",
    "mypurecloud.com.au",
    "sae1.pure.cloud",
    "mec1.pure.cloud",
]

DEFAULT_REGION = "mypurecloud.ie"

_GUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"


@dataclass
class Settings:
    client_id: str
    client_secret: str
    region: str = DEFAULT_REGION

    @property
    def api_base(self) -> str:
        return f"https://api.{self.region}"

    @property
    def login_base(self) -> str:
        return f"https://login.{self.region}"


@dataclass
class Target:
    """What the user pointed us at: an IVR entity, a flow, or neither."""

    kind: str            # "ivr" | "flow" | "unknown"
    entity_id: str | None
    region: str | None   # inferred from the URL host when one was supplied


def load_dotenv_if_present(path: str = ".env") -> None:
    """Load a .env file without requiring python-dotenv to be installed."""
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(path)
        return
    except ImportError:
        pass

    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def settings_from_env(region_override: str | None = None) -> Settings:
    client_id = os.environ.get("GENESYS_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GENESYS_CLIENT_SECRET", "").strip()
    region = (region_override or os.environ.get("GENESYS_REGION") or DEFAULT_REGION).strip()

    missing = [n for n, v in (("GENESYS_CLIENT_ID", client_id),
                              ("GENESYS_CLIENT_SECRET", client_secret)) if not v]
    if missing:
        raise SystemExit(
            "Missing credentials: " + ", ".join(missing) + ".\n"
            "Copy .env.example to .env and fill in your OAuth client, or export them "
            "as environment variables."
        )
    return Settings(client_id=client_id, client_secret=client_secret,
                    region=normalise_region(region))


_REGION_OK = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


def normalise_region(region: str) -> str:
    """Reduce whatever the user supplied to a bare region domain.

    Accepts a full console URL or a hostname and strips any `apps.`/`api.`/
    `login.` prefix. The result must look like a hostname -- the region is
    concatenated into every request URL, so anything containing a slash,
    userinfo, port or whitespace is rejected rather than normalised, to keep a
    malformed value from redirecting requests somewhere unintended.
    """
    region = (region or "").strip().lower()
    if region.startswith("http"):
        region = urlparse(region).netloc
    region = re.sub(r"^(apps?|api|login)\.", "", region).strip("/")
    if not _REGION_OK.match(region):
        raise SystemExit(
            f"'{region}' is not a valid Genesys region domain. Use one of: "
            + ", ".join(KNOWN_REGIONS)
        )
    return region


def parse_console_url(url: str) -> Target:
    """Turn a Genesys Cloud admin URL into a target we can fetch.

    Handles the two shapes that matter:
      .../directory/#/admin/routing/ivrs/<guid>        -> an IVR (call route) entity
      .../directory/#/admin/architect/flows/<guid>     -> a flow
    """
    parsed = urlparse(url)
    host = parsed.netloc
    region = re.sub(r"^apps?\.", "", host) if host else None
    if region and region not in KNOWN_REGIONS:
        # Still usable — Genesys adds regions faster than any hard-coded list.
        pass

    blob = f"{parsed.path}{parsed.params}{parsed.query}{parsed.fragment}"
    ids = re.findall(_GUID, blob)
    entity_id = ids[-1] if ids else None

    lowered = blob.lower()
    if "/ivrs" in lowered:
        kind = "ivr"
    elif "flow" in lowered or "architect" in lowered:
        kind = "flow"
    else:
        kind = "unknown"

    return Target(kind=kind, entity_id=entity_id, region=region)
