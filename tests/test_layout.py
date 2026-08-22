"""The output tree: a folder per route, per flow, per artefact type.

Run with:  python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from genesys_flow_doc import layout, parse
from genesys_flow_doc.cli import write_outputs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "samples", "example-flow.json")


class SlugTests(unittest.TestCase):
    def test_names_reduce_to_safe_slugs(self):
        self.assertEqual(layout.slugify("Customer Care IVR By Claude"),
                         "customer-care-ivr-by-claude")
        self.assertEqual(layout.slugify("Prepaid - Top Up"), "prepaid-top-up")
        self.assertEqual(layout.slugify("  SABIC SIP +44 800 456 1743  "),
                         "sabic-sip-44-800-456-1743")

    def test_a_slug_cannot_escape_its_directory(self):
        for hostile in ("../../etc/passwd", r"..\..\windows", "C:\\evil", "a/b/c", "..."):
            slug = layout.slugify(hostile)
            self.assertNotIn("/", slug)
            self.assertNotIn("\\", slug)
            self.assertNotIn("..", slug)
            self.assertRegex(slug, r"^[a-z0-9-]+$")

    def test_windows_reserved_names_are_avoided(self):
        for reserved in ("CON", "com1", "LPT9", "nul"):
            self.assertNotIn(layout.slugify(reserved).upper(),
                             {"CON", "COM1", "LPT9", "NUL"})

    def test_an_empty_name_falls_back(self):
        self.assertEqual(layout.slugify("", "flow"), "flow")
        self.assertEqual(layout.slugify("!!!", "flow"), "flow")


class DestinationTests(unittest.TestCase):
    def test_a_routed_flow_nests_under_its_route(self):
        dest = layout.Destination.for_flow("out", "Customer Care IVR", "testt call")
        self.assertEqual(dest.base.replace(os.sep, "/"),
                         "out/routes/testt-call/customer-care-ivr")

    def test_an_unrouted_flow_sits_under_flows(self):
        dest = layout.Destination.for_flow("out", "Customer Care IVR")
        self.assertEqual(dest.base.replace(os.sep, "/"),
                         "out/flows/customer-care-ivr")

    def test_each_artefact_type_gets_its_own_folder(self):
        dest = layout.Destination.for_flow("out", "Main IVR", "Route A")
        self.assertEqual(
            dest.path_for(layout.PDF, "business.pdf").replace(os.sep, "/"),
            "out/routes/route-a/main-ivr/pdf/main-ivr.business.pdf")
        self.assertEqual(
            dest.path_for(layout.RAW, "raw.json").replace(os.sep, "/"),
            "out/routes/route-a/main-ivr/raw/main-ivr.raw.json")

    def test_filenames_keep_the_flow_name_for_when_they_are_detached(self):
        dest = layout.Destination.for_flow("out", "Main IVR", "Route A")
        for kind, suffix in ((layout.HTML, "business.html"), (layout.PDF, "technical.pdf")):
            self.assertTrue(os.path.basename(dest.path_for(kind, suffix)).startswith("main-ivr."))

    def test_index_links_are_posix_relative_paths(self):
        dest = layout.Destination.for_flow("out", "Main IVR", "Route A")
        link = dest.relative_to_root(layout.HTML, "business.html")
        self.assertEqual(link, "routes/route-a/main-ivr/html/main-ivr.business.html")
        self.assertNotIn("\\", link)


class WriteOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIXTURE, encoding="utf-8") as handle:
            cls.doc = parse.parse_flow(json.load(handle))

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="flowdoc-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _relative(self, paths):
        return sorted(os.path.relpath(p, self.tmp).replace(os.sep, "/") for p in paths)

    def test_both_formats_land_in_their_own_folders(self):
        dest = layout.Destination.for_flow(self.tmp, self.doc.name, "Some Route")
        written = write_outputs(self.doc, dest, False, {"html", "md"})
        self.assertEqual(self._relative(written), [
            "routes/some-route/acme-main-ivr/diagram/acme-main-ivr.flow.mmd",
            "routes/some-route/acme-main-ivr/html/acme-main-ivr.business.html",
            "routes/some-route/acme-main-ivr/html/acme-main-ivr.technical.html",
            "routes/some-route/acme-main-ivr/markdown/acme-main-ivr.business.md",
            "routes/some-route/acme-main-ivr/markdown/acme-main-ivr.technical.md",
            "routes/some-route/acme-main-ivr/raw/acme-main-ivr.raw.json",
        ])
        for path in written:
            self.assertTrue(os.path.getsize(path) > 0, path)

    def test_html_only_writes_no_markdown_folder(self):
        dest = layout.Destination.for_flow(self.tmp, self.doc.name, "Some Route")
        write_outputs(self.doc, dest, False, {"html"})
        self.assertFalse(os.path.isdir(dest.dir_for(layout.MARKDOWN)))
        self.assertTrue(os.path.isdir(dest.dir_for(layout.HTML)))
        # The raw configuration is always kept, so a rebuild is always possible.
        self.assertTrue(os.path.isfile(dest.path_for(layout.RAW, "raw.json")))

    def test_the_same_flow_under_two_routes_does_not_collide(self):
        first = layout.Destination.for_flow(self.tmp, self.doc.name, "Route One")
        second = layout.Destination.for_flow(self.tmp, self.doc.name, "Route Two")
        write_outputs(self.doc, first, False, {"html"})
        write_outputs(self.doc, second, False, {"html"})
        self.assertNotEqual(first.base, second.base)
        for dest in (first, second):
            self.assertTrue(os.path.isfile(dest.path_for(layout.HTML, "business.html")))


if __name__ == "__main__":
    unittest.main()
