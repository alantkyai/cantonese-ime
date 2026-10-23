"""Composition behavior verified independently of dictionary and frontend."""

from dataclasses import dataclass
import unittest

from cantonese_ime.session import Session


@dataclass(frozen=True)
class FakeCandidate:
    text: str
    reading: str = "nei5"
    score: float = 1.0
    match_type: str = "exact"
    consumed_input: int = 3


class FakeEngine:
    def __init__(self, count=12):
        self.entries = [FakeCandidate(f"字{index}") for index in range(count)]
        self.lookups = []
        self.selections = []

    def lookup(self, raw, limit=9, mode=None):
        self.lookups.append((raw, limit, mode))
        return self.entries[:limit]

    def record_selection(self, raw, candidate, mode=None):
        self.selections.append((raw, candidate, mode))


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.engine = FakeEngine()
        self.session = Session(self.engine)

    def compose(self, raw="nei", session=None):
        session = session or self.session
        for character in raw:
            result = session.handle_key(character)
            self.assertTrue(result.handled)
        return result

    def test_typing_preserves_case_and_apostrophes_and_forwards_mode(self):
        result = self.compose("Nei'Ho")
        self.assertEqual(result.preedit, "Nei'Ho")
        self.assertEqual(self.session.buffer, "Nei'Ho")
        self.assertEqual(len(result.candidates), 9)
        self.assertEqual(self.engine.lookups[-1], ("Nei'Ho", 90, "forgiving"))
        self.assertEqual((result.page, result.selected_index), (0, 0))

    def test_number_selects_slot_on_current_page(self):
        self.compose()
        page = self.session.handle_key("PageDown")
        self.assertEqual((page.page, page.selected_index), (1, 0))
        self.assertEqual([candidate.text for candidate in page.candidates], ["字9", "字10", "字11"])
        result = self.session.handle_key("2")
        self.assertEqual(result.committed, "字10")
        self.assertEqual((result.preedit, result.candidates, result.page, result.selected_index), ("", (), 0, 0))
        self.assertEqual(self.engine.selections, [])

    def test_space_commits_highlight_and_learning_requires_opt_in(self):
        self.session.learn = True
        self.compose()
        self.session.handle_key("Down")
        result = self.session.handle_key(" ")
        self.assertEqual(result.committed, "字1")
        self.assertEqual(self.engine.selections, [("nei", self.engine.entries[1], "forgiving")])

    def test_enter_commits_exact_raw_text_without_learning(self):
        self.session.learn = True
        self.compose("Nei'Ho")
        result = self.session.handle_key("Enter")
        self.assertEqual(result.committed, "Nei'Ho")
        self.assertEqual(result.preedit, "")
        self.assertEqual(self.engine.selections, [])

    def test_cancel_reset_and_mode_change_discard_without_learning(self):
        self.session.learn = True
        self.compose()
        result = self.session.handle_key("Escape")
        self.assertEqual((result.committed, result.preedit, result.candidates), ("", "", ()))
        self.compose()
        self.session.reset()
        self.assertEqual((self.session.buffer, self.session.candidates), ("", ()))
        self.compose()
        self.session.set_mode("jyutping")
        self.assertEqual(self.session.mode, "jyutping")
        self.assertEqual((self.session.buffer, self.session.candidates), ("", ()))
        self.compose("ho")
        self.assertEqual(self.engine.lookups[-1], ("ho", 90, "jyutping"))
        self.assertEqual(self.engine.selections, [])

    def test_backspace_updates_candidates_and_clears_last_character(self):
        self.compose("ne")
        self.session.handle_key("PageDown")
        result = self.session.handle_key("Backspace")
        self.assertEqual((result.preedit, result.page, result.selected_index), ("n", 0, 0))
        self.assertEqual(self.engine.lookups[-1][0], "n")
        lookup_count = len(self.engine.lookups)
        result = self.session.handle_key("\b")
        self.assertEqual((result.preedit, result.candidates), ("", ()))
        self.assertEqual(len(self.engine.lookups), lookup_count)
        self.assertFalse(self.session.handle_key("Backspace").handled)

    def test_navigation_crosses_pages_and_clamps_at_ends(self):
        self.compose()
        self.session.handle_key("Up")
        self.assertEqual((self.session.page, self.session.selected_index), (0, 0))
        for _ in range(10):
            result = self.session.handle_key("Down")
        self.assertEqual((result.page, result.selected_index), (1, 1))
        result = self.session.handle_key("PageUp")
        self.assertEqual((result.page, result.selected_index), (0, 1))
        for _ in range(20):
            result = self.session.handle_key("Down")
        self.assertEqual((result.page, result.selected_index), (1, 2))
        result = self.session.handle_key("PageDown")
        self.assertEqual((result.page, result.selected_index), (1, 2))

    def test_invalid_number_slots_and_zero_do_not_change_composition(self):
        self.compose()
        before = self.session.handle_key("PageDown")
        for digit in ("0", "4", "9"):
            result = self.session.handle_key(digit)
            self.assertTrue(result.handled)
            self.assertEqual((result.preedit, result.candidates, result.page, result.selected_index), (before.preedit, before.candidates, before.page, before.selected_index))
            self.assertEqual(result.committed, "")

    def test_empty_composition_passes_through_application_keys(self):
        for key in ("0", "1", "9", "Space", "Enter", "Escape", "Backspace", "Up", "Down", "PageUp", "PageDown", "Tab"):
            result = self.session.handle_key(key)
            self.assertFalse(result.handled, key)
            self.assertEqual((result.preedit, result.committed), ("", ""))

    def test_unsupported_keys_pass_through_without_mutation(self):
        before = self.compose()
        for key in ("Left", "Right", "ArrowLeft", "Ctrl+A", "Alt+Space", "Tab", "Shift", "F1", ".", "你", ""):
            result = self.session.handle_key(key)
            self.assertFalse(result.handled, key)
            self.assertEqual((result.preedit, result.candidates, result.page, result.selected_index), (before.preedit, before.candidates, before.page, before.selected_index))

    def test_input_bound_preserves_composition_and_allows_recovery(self):
        session = Session(self.engine, max_input_length=3)
        before = self.compose("nei", session)
        result = session.handle_key("h")
        self.assertTrue(result.handled)
        self.assertEqual((result.preedit, result.candidates), (before.preedit, before.candidates))
        session.handle_key("Backspace")
        result = session.handle_key("w")
        self.assertEqual(result.preedit, "new")

    def test_default_input_bound_is_256_characters(self):
        result = self.compose("a" * 257)
        self.assertEqual(result.preedit, "a" * 256)
        self.assertEqual(len(self.engine.lookups), 256)

    def test_empty_candidates_keep_preedit_until_explicit_commit_or_cancel(self):
        session = Session(FakeEngine(count=0))
        self.compose(session=session)
        for key in ("Space", "1", "0", "Up", "Down", "PageUp", "PageDown"):
            result = session.handle_key(key)
            self.assertTrue(result.handled)
            self.assertEqual((result.preedit, result.committed, result.candidates, result.page, result.selected_index), ("nei", "", (), 0, 0))
        self.assertEqual(session.handle_key("Enter").committed, "nei")

    def test_smaller_pages_select_and_clamp_partial_final_page(self):
        session = Session(FakeEngine(count=5), page_size=3)
        self.compose(session=session)
        session.handle_key("Down")
        session.handle_key("Down")
        result = session.handle_key("PageDown")
        self.assertEqual((result.page, result.selected_index), (1, 1))
        self.assertEqual(session.handle_key("2").committed, "字4")

    def test_invalid_configuration_does_not_cancel_existing_composition(self):
        for mode in ("strict", "", None):
            with self.assertRaises(ValueError):
                Session(self.engine, mode=mode)
        for page_size in (0, 10, True, 1.5):
            with self.assertRaises(ValueError):
                Session(self.engine, page_size=page_size)
        for max_input_length in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                Session(self.engine, max_input_length=max_input_length)
        self.compose()
        with self.assertRaises(ValueError):
            self.session.set_mode("invalid")
        self.assertEqual(self.session.buffer, "nei")

    def test_lookup_failure_preserves_existing_state(self):
        before = self.compose()

        def failed_lookup(*args, **kwargs):
            raise RuntimeError("lookup unavailable")

        self.engine.lookup = failed_lookup
        with self.assertRaises(RuntimeError):
            self.session.handle_key("h")
        self.assertEqual((self.session.buffer, self.session.candidates), (before.preedit, before.candidates))


if __name__ == "__main__":
    unittest.main()
