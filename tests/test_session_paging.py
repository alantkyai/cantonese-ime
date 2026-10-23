"""Later homophone pages remain selectable without eager full-list loading."""

from dataclasses import dataclass
import unittest

from cantonese_ime.session import Session


@dataclass(frozen=True)
class Item:
    text: str
    reading: str = "lei4"
    score: float = 0


@dataclass(frozen=True)
class Page:
    candidates: tuple[Item, ...]
    offset: int
    next_offset: int | None


class PagedEngine:
    def __init__(self, count=125):
        self.items = tuple(Item(f"字{index}") for index in range(count))
        self.requests = []
        self.selections = []
        self.fail = False
        self.overlap = False

    def lookup_page(self, raw, *, offset=0, page_size=9, mode=None):
        self.requests.append((raw, offset, page_size, mode))
        if self.fail:
            raise OSError("page unavailable")
        items = self.items[offset:offset + page_size]
        if self.overlap and offset:
            items = (self.items[0],) + items[1:]
        end = offset + len(items)
        return Page(items, offset, end if end < len(self.items) else None)

    def record_selection(self, raw, candidate, mode=None):
        self.selections.append((raw, candidate.text, mode))


class SessionPagingTests(unittest.TestCase):
    def test_later_than_90_candidate_can_be_selected_and_learned(self):
        engine = PagedEngine()
        session = Session(engine, mode="jyutping", learn=True)
        session.handle_key("l")
        self.assertEqual(engine.requests, [("l", 0, 9, "jyutping")])
        for _ in range(12):
            session.handle_key("PageDown")
        self.assertEqual(session.page, 12)
        self.assertEqual(session.candidates[3].text, "字111")
        committed = session.handle_key("4")
        self.assertEqual(committed.committed, "字111")
        self.assertEqual(engine.selections, [("l", "字111", "jyutping")])
        self.assertEqual((session.buffer, session.candidates, session.page), ("", (), 0))

    def test_down_fetches_on_demand_and_backtracking_uses_loaded_pages(self):
        engine = PagedEngine(20)
        session = Session(engine, page_size=4)
        session.handle_key("l")
        for _ in range(3):
            session.handle_key("Down")
        self.assertEqual(len(engine.requests), 1)
        session.handle_key("Down")
        self.assertEqual(len(engine.requests), 2)
        session.handle_key("PageUp")
        session.handle_key("PageDown")
        self.assertEqual(len(engine.requests), 2)
        for _ in range(30):
            result = session.handle_key("Down")
        self.assertEqual((result.page, result.selected_index), (4, 3))
        requests = len(engine.requests)
        session.handle_key("PageDown")
        self.assertEqual(len(engine.requests), requests)

    def test_fetch_failure_and_overlapping_page_preserve_visible_state(self):
        engine = PagedEngine()
        session = Session(engine)
        before = session.handle_key("l")
        engine.fail = True
        with self.assertRaises(OSError):
            session.handle_key("PageDown")
        self.assertEqual((session.buffer, session.candidates, session.page), (before.preedit, before.candidates, before.page))
        engine.fail = False
        engine.overlap = True
        with self.assertRaises(ValueError):
            session.handle_key("PageDown")
        self.assertEqual(session.candidates, before.candidates)
        engine.overlap = False
        session.handle_key("PageDown")
        self.assertEqual(session.page, 1)

    def test_new_input_mode_or_cancel_discards_later_pages(self):
        engine = PagedEngine()
        session = Session(engine)
        session.handle_key("l")
        session.handle_key("PageDown")
        session.handle_key("e")
        self.assertEqual(engine.requests[-1][1], 0)
        self.assertEqual(session.page, 0)
        session.set_mode("jyutping")
        session.handle_key("i")
        self.assertEqual(engine.requests[-1], ("i", 0, 9, "jyutping"))
        session.handle_key("Escape")
        self.assertFalse(session.handle_key("PageDown").handled)


if __name__ == "__main__":
    unittest.main()
