"""Guard the parser against the shapes Architect actually publishes.

`samples/example-flow.json` is a small synthetic flow written in the real
Architect configuration schema (action graph, `flowSequenceItemList`, value
objects, `uiMetaData.sequenceItems`), so these tests exercise the same code
paths a live flow does.

Run with:  python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from genesys_flow_doc import mermaid, parse, render_business, render_technical
from genesys_flow_doc.config import parse_console_url

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "samples", "example-flow.json")


def load() -> "parse.FlowDoc":
    with open(FIXTURE, encoding="utf-8") as handle:
        return parse.parse_flow(json.load(handle))


class FlowIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = load()

    def test_identity(self):
        self.assertEqual(self.doc.name, "Acme Main IVR")
        self.assertEqual(self.doc.flow_type, "inboundcall")
        self.assertEqual(self.doc.default_language, "en-US")
        self.assertEqual(self.doc.supported_languages, ["en-US"])

    def test_entry_point_is_the_initial_sequence_and_sorts_first(self):
        self.assertEqual(self.doc.start_ref, "Opening Checks")
        self.assertTrue(self.doc.containers[0].is_start)
        self.assertEqual(self.doc.containers[0].name, "Opening Checks")
        self.assertEqual(sum(1 for c in self.doc.containers if c.is_start), 1)

    def test_all_stages_are_found(self):
        self.assertCountEqual([c.name for c in self.doc.containers],
                              ["Opening Checks", "Main Menu", "Transfer Failed"])
        self.assertEqual([c.kind for c in self.doc.containers if c.name == "Main Menu"], ["Menu"])

    def test_variables_carry_scope(self):
        names = [v["name"] for v in self.doc.variables]
        self.assertIn("Flow.callerIntent", names)
        callers = next(v for v in self.doc.variables if v["name"] == "Flow.callerIntent")
        self.assertEqual(callers["type"], "Text")
        self.assertEqual(callers["scope"], "Flow")
        self.assertTrue(callers["output"])

    def test_manifest_supplies_dependencies_without_api_calls(self):
        self.assertEqual(self.doc.references["Queues"],
                         ["Acme Sales", "Acme Technical Support"])
        self.assertEqual(self.doc.references["Data actions"], ["Look Up Account"])
        self.assertEqual(self.doc.name_by_id["11111111-1111-4111-8111-111111111111"],
                         "Acme Sales")

    def test_every_action_type_is_recognised(self):
        self.assertEqual(self.doc.unmapped_kinds, [])


class GraphWalkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = load()
        cls.stages = {c.name: c for c in cls.doc.containers}

    def test_paths_become_labelled_branches(self):
        schedule = self.stages["Opening Checks"].nodes[0]
        self.assertEqual(schedule.kind, "EvaluateScheduleAction")
        self.assertEqual([b.label for b in schedule.branches], ["Active", "Inactive"])

    def test_next_action_chains_within_a_branch(self):
        schedule = self.stages["Opening Checks"].nodes[0]
        closed = next(b for b in schedule.branches if b.label == "Inactive")
        self.assertEqual([n.name for n in closed.nodes], ["Closed Message", "End Closed Call"])

    def test_unreachable_actions_are_reported_not_dropped(self):
        orphans = [n for n in self.doc.all_nodes() if n.unreachable]
        self.assertEqual([n.name for n in orphans], ["Orphaned Announcement"])

    def test_menu_choices_carry_their_digit(self):
        menu = self.stages["Main Menu"]
        self.assertEqual([n.dtmf for n in menu.nodes], ["1", "2", "3", "(no valid choice)"])
        self.assertEqual([n.name for n in menu.nodes][:3], ["Sales", "Support", "Accounts"])

    def test_cross_stage_target_is_a_jump_not_an_inline_copy(self):
        sales = self.stages["Main Menu"].nodes[0]
        self.assertTrue(any("Apologise" in j for j in sales.jumps), sales.jumps)
        # ...and the target is still documented once, in its own stage.
        self.assertEqual([n.name for n in self.stages["Transfer Failed"].nodes],
                         ["Apologise", "End Call"])

    def test_stage_reference_is_resolved_to_a_name(self):
        jump = self.stages["Opening Checks"].nodes[0].branches[0].nodes[0]
        self.assertEqual(jump.kind, "TransferMenuAction")
        self.assertIn("Main Menu", jump.jumps)

    def test_value_objects_yield_readable_properties(self):
        sales = self.stages["Main Menu"].nodes[0]
        self.assertEqual(dict(sales.props)["queues[0]"], "Acme Sales")


class SpeechTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = load()

    def test_literal_tts_comes_from_sequence_items(self):
        spoken = [s.value for s in self.doc.all_speech() if s.kind == "tts"]
        self.assertIn("Welcome to Acme. For sales press 1, for support press 2.", spoken)
        self.assertIn("We are closed. Our hours are nine to five, Monday to Friday.", spoken)

    def test_prompt_references_are_identified(self):
        prompts = [s.value for s in self.doc.all_speech() if s.kind == "prompt"]
        self.assertIn("salesGreeting", prompts)

    def test_language_variants_are_labelled(self):
        arabic = [s.value for s in self.doc.all_speech() if "ar-AE" in s.value]
        self.assertTrue(arabic, "the Arabic audio case should be captured")

    def test_pauses_are_captured_separately_from_words(self):
        pauses = [s for s in self.doc.all_speech() if s.kind == "pause"]
        self.assertEqual(len(pauses), 1)
        self.assertIn("0.5 seconds", pauses[0].value)


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = load()
        cls.business = render_business.render(cls.doc)
        cls.technical = render_technical.render(cls.doc)

    def test_business_document_avoids_jargon(self):
        for jargon in ("TransferPureMatchAction", "__type", "trackingId",
                       "ToAudioTTS", "sequenceItems"):
            self.assertNotIn(jargon, self.business)

    def test_business_document_names_real_destinations(self):
        self.assertIn("**Acme Sales** queue", self.business)
        self.assertIn("**+35315550123**", self.business)
        self.assertIn("Acme Working Hours", self.business)

    def test_business_document_quotes_the_script(self):
        self.assertIn("Welcome to Acme. For sales press 1, for support press 2.", self.business)

    def test_technical_document_keeps_raw_detail(self):
        self.assertIn("`TransferPureMatchAction`", self.technical)
        self.assertIn("queues[0]", self.technical)
        self.assertIn("Tracking ID", self.technical)

    def test_technical_document_flags_unreachable_configuration(self):
        self.assertIn("cannot be reached", self.technical)

    def test_menu_choices_fan_out_rather_than_chain(self):
        diagram = mermaid.render(self.doc)
        self.assertIn('|"press 1"|', diagram)
        self.assertNotIn("n2 --> n3", diagram)


class UrlTests(unittest.TestCase):
    def test_ivr_url(self):
        target = parse_console_url(
            "https://apps.mypurecloud.ie/directory/#/admin/routing/ivrs/"
            "5ffacb01-3ae5-49e9-8e54-58d4f32c76f7")
        self.assertEqual(target.kind, "ivr")
        self.assertEqual(target.entity_id, "5ffacb01-3ae5-49e9-8e54-58d4f32c76f7")
        self.assertEqual(target.region, "mypurecloud.ie")

    def test_flow_url(self):
        target = parse_console_url(
            "https://apps.mypurecloud.com/architect/#/inboundcall/flows/"
            "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/latest")
        self.assertEqual(target.kind, "flow")
        self.assertEqual(target.region, "mypurecloud.com")


if __name__ == "__main__":
    unittest.main()
