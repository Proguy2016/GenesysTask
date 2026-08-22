"""Enforce the read-only guarantee against the source, not just by convention.

These tests fail if anyone later adds a write path, widens the host checks, or
lets untrusted configuration text reach a report as markup.

Run with:  python -m unittest discover -s tests
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from genesys_flow_doc import parse, render_html
from genesys_flow_doc.client import GenesysClient, ReadOnlyViolation
from genesys_flow_doc.config import Settings, normalise_region

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(ROOT, "genesys_flow_doc")
SOURCES = sorted(glob.glob(os.path.join(PACKAGE, "*.py")))

SETTINGS = Settings(client_id="id", client_secret="secret", region="mypurecloud.ie")


def source_of(filename: str) -> str:
    with open(os.path.join(PACKAGE, filename), encoding="utf-8") as handle:
        return handle.read()


class WriteVerbTests(unittest.TestCase):
    """Nothing in the package may issue a mutating HTTP request."""

    MUTATING = re.compile(r"\.(post|put|patch|delete)\s*\(", re.IGNORECASE)

    def test_no_mutating_verbs_outside_the_token_exchange(self):
        offenders = []
        for path in SOURCES:
            with open(path, encoding="utf-8") as handle:
                for number, line in enumerate(handle, start=1):
                    if line.lstrip().startswith("#"):
                        continue
                    if self.MUTATING.search(line):
                        offenders.append(f"{os.path.basename(path)}:{number}: {line.strip()}")
        # The single permitted exception is the OAuth token request, which
        # RFC 6749 requires to be a POST to the login host.
        self.assertEqual(len(offenders), 1, f"unexpected write calls: {offenders}")
        self.assertIn("client.py", offenders[0])
        self.assertIn("session.post", offenders[0])

    def test_the_only_post_targets_the_login_host(self):
        body = source_of("client.py")
        post_at = body.index("self.session.post(")
        window = body[post_at - 400:post_at + 200]
        self.assertIn("login_base", window)
        self.assertNotIn("api_base", window)

    def test_every_api_path_is_reached_through_get(self):
        for path in SOURCES:
            with open(path, encoding="utf-8") as handle:
                for number, line in enumerate(handle, start=1):
                    if "/api/v2/" not in line or line.lstrip().startswith(("#", '"', "*")):
                        continue
                    if "get(" in line or "get_optional(" in line or "paged(" in line:
                        continue
                    # Anything else mentioning an API path must be documentation
                    # or a display string, never a call.
                    self.assertNotRegex(
                        line, r"self\.(client|session)\.\w+\(",
                        f"{os.path.basename(path)}:{number} reaches an API path outside get()")


class HostRestrictionTests(unittest.TestCase):
    def setUp(self):
        self.client = GenesysClient(SETTINGS)

    def test_relative_paths_resolve_to_the_configured_region(self):
        self.assertEqual(self.client._resolve("/api/v2/flows"),
                         "https://api.mypurecloud.ie/api/v2/flows")

    def test_another_host_is_refused(self):
        with self.assertRaises(ReadOnlyViolation):
            self.client._resolve("https://evil.example.com/api/v2/flows")

    def test_a_different_genesys_region_is_refused(self):
        with self.assertRaises(ReadOnlyViolation):
            self.client._resolve("https://api.mypurecloud.com/api/v2/flows")

    def test_plain_http_is_refused(self):
        with self.assertRaises(ReadOnlyViolation):
            self.client._resolve("http://api.mypurecloud.ie/api/v2/flows")

    def test_download_rejects_hosts_outside_the_allowlist(self):
        for url in ("https://evil.example.com/config.json",
                    "http://api.mypurecloud.ie/config.json",
                    "file:///etc/passwd"):
            with self.assertRaises(ReadOnlyViolation, msg=url):
                self.client.download(url)


class RegionValidationTests(unittest.TestCase):
    def test_prefixes_and_urls_are_reduced_to_the_domain(self):
        for value in ("mypurecloud.ie", "apps.mypurecloud.ie", "api.mypurecloud.ie",
                      "https://apps.mypurecloud.ie/directory/#/admin"):
            self.assertEqual(normalise_region(value), "mypurecloud.ie")

    def test_malformed_regions_are_refused(self):
        for value in ("", "not a host", "host/path", "user@host.com", "host:8080",
                      "../../etc", "mypurecloud"):
            with self.assertRaises(SystemExit, msg=value):
                normalise_region(value)


class SecretHandlingTests(unittest.TestCase):
    def test_credentials_are_never_logged(self):
        body = source_of("client.py")
        for line in body.splitlines():
            if "log." in line:
                self.assertNotIn("client_secret", line)
                self.assertNotIn("_token", line)
                self.assertNotIn("basic", line.lower())

    def test_no_credential_is_written_to_any_output(self):
        for path in SOURCES:
            with open(path, encoding="utf-8") as handle:
                body = handle.read()
            if os.path.basename(path) in ("client.py", "config.py"):
                continue
            self.assertNotIn("client_secret", body, os.path.basename(path))


class InjectionTests(unittest.TestCase):
    """Configuration text is untrusted input; it must never become markup."""

    def test_phrase_escapes_markup_but_keeps_emphasis(self):
        rendered = render_html.phrase('The **<script>alert(1)</script>** queue.')
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("<strong>", rendered)

    def test_a_hostile_queue_name_cannot_inject_into_a_report(self):
        with open(os.path.join(ROOT, "samples", "example-flow.json"), encoding="utf-8") as fh:
            config = json.load(fh)
        payload = '<img src=x onerror="alert(1)">'
        menu = next(s for s in config["flowSequenceItemList"] if s["__type"] == "Menu")
        queue = menu["menuChoiceList"][0]["action"]["queues"][0]
        queue["text"] = payload
        queue["config"]["lit"]["text"] = payload
        config["manifest"]["queue"][0]["name"] = payload

        doc = parse.parse_flow(config)
        for page in (render_html.render_business(doc), render_html.render_technical(doc)):
            # The payload must survive only as text. Checking for "onerror=" alone
            # would be a false positive, since the escaped form legitimately
            # contains it as `onerror=&quot;`; what matters is that no `<img`
            # tag is ever opened.
            self.assertNotIn("<img", page)
            self.assertIn("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;", page)

    def test_flow_name_cannot_break_out_of_the_title(self):
        with open(os.path.join(ROOT, "samples", "example-flow.json"), encoding="utf-8") as fh:
            config = json.load(fh)
        config["name"] = "</title><script>alert(1)</script>"
        page = render_html.render_business(parse.parse_flow(config))
        self.assertNotIn("<script>", page)


class OutputPathTests(unittest.TestCase):
    def test_slugify_cannot_escape_the_output_directory(self):
        from genesys_flow_doc.cli import slugify

        for hostile in ("../../etc/passwd", "..\\..\\windows", "a/b/c", "C:\\evil"):
            slug = slugify(hostile)
            self.assertNotIn("/", slug)
            self.assertNotIn("\\", slug)
            self.assertNotIn("..", slug)
            self.assertRegex(slug, r"^[a-z0-9-]+$")


if __name__ == "__main__":
    unittest.main()
