"""Frontend-independent composition and candidate-selection state.

Pages and selection indexes are zero based. Public ``candidates`` contains only
the current page; additional pages are fetched when navigation needs them and
cached for backtracking. Legacy engines may return a fixed candidate list. Sessions
accept ASCII letters and apostrophe boundaries. Digits select candidates rather
than entering tones, which can still be supplied directly to the lookup engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from .engine import MAX_INPUT_LENGTH

if TYPE_CHECKING:
    from .engine import Candidate


class LookupEngine(Protocol):
    def lookup(
        self, raw: str, limit: int = 9, mode: str | None = None
    ) -> list[Candidate]: ...


@dataclass(frozen=True)
class SessionResult:
    handled: bool
    committed: str
    preedit: str
    candidates: tuple[Candidate, ...]
    selected_index: int
    page: int
    has_more: bool = False
    completion_truncated: bool = False


class Session:
    """Maintain a composition without depending on a window or keyboard API."""

    MAX_CANDIDATES = 90
    MODES = frozenset({"jyutping", "forgiving"})

    def __init__(
        self,
        engine: LookupEngine,
        mode: str = "forgiving",
        page_size: int = 9,
        learn: bool = False,
        max_input_length: int = MAX_INPUT_LENGTH,
    ) -> None:
        self._validate_mode(mode)
        if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 9:
            raise ValueError("page_size must be an integer between 1 and 9")
        if isinstance(max_input_length, bool) or not isinstance(max_input_length, int) or max_input_length < 1:
            raise ValueError("max_input_length must be a positive integer")
        self.engine = engine
        self._mode = mode
        self.page_size = page_size
        self.learn = learn
        self.max_input_length = max_input_length
        self._buffer = ""
        self._all_candidates: tuple[Candidate, ...] = ()
        self._highlight = 0
        self._next_offset: int | None = None
        self._completion_truncated = False

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def buffer(self) -> str:
        return self._buffer

    @property
    def candidates(self) -> tuple[Candidate, ...]:
        start = self.page * self.page_size
        return self._all_candidates[start : start + self.page_size]

    @property
    def page(self) -> int:
        return self._highlight // self.page_size

    @property
    def selected_index(self) -> int:
        return self._highlight % self.page_size

    @property
    def has_more(self) -> bool:
        return ((self.page + 1) * self.page_size < len(self._all_candidates)
                or self._next_offset is not None)

    @property
    def completion_truncated(self) -> bool:
        return self._completion_truncated

    def reset(self) -> None:
        """Cancel the current composition, for example after a focus change."""
        self._buffer = ""
        self._all_candidates = ()
        self._highlight = 0
        self._next_offset = None
        self._completion_truncated = False

    def set_mode(self, mode: str) -> None:
        """Validate the mode and cancel composition before using it."""
        self._validate_mode(mode)
        self.reset()
        self._mode = mode

    def handle_key(self, key: str) -> SessionResult:
        """Process one key; an unhandled key never changes composition state.

        Named keys are case insensitive. Control/Alt shortcuts and Left/Right
        are deliberately unhandled so a future frontend can retain its normal
        application behavior. At the input bound, additional letters and
        apostrophes are consumed without losing the existing composition.
        """
        if not isinstance(key, str):
            raise TypeError("key must be a string")

        if len(key) == 1 and ("a" <= key <= "z" or "A" <= key <= "Z" or key == "'"):
            if len(self._buffer) < self.max_input_length:
                self._replace_buffer(self._buffer + key)
            return self._result(True)

        if not self._buffer:
            return self._result(False)

        if len(key) == 1 and "0" <= key <= "9":
            slot = int(key) - 1
            if 0 <= slot < len(self.candidates):
                return self._select(self.page * self.page_size + slot)
            return self._result(True)

        named_key = key.casefold()
        if named_key in {"space", " "}:
            if self._all_candidates:
                return self._select(self._highlight)
            # No candidate should cause an accidental Latin commit. Enter is
            # the explicit way to commit the raw text.
            return self._result(True)
        if named_key in {"enter", "return", "\r", "\n"}:
            committed = self._buffer
            self.reset()
            return self._result(True, committed)
        if named_key in {"escape", "esc", "\x1b"}:
            self.reset()
            return self._result(True)
        if named_key in {"backspace", "\b"}:
            self._replace_buffer(self._buffer[:-1])
            return self._result(True)
        if named_key == "up":
            self._highlight = max(0, self._highlight - 1)
            return self._result(True)
        if named_key == "down":
            self._ensure_candidate(self._highlight + 1)
            self._highlight = min(max(0, len(self._all_candidates) - 1), self._highlight + 1)
            return self._result(True)
        if named_key in {"pageup", "pagedown"}:
            if self._all_candidates:
                direction = -1 if named_key == "pageup" else 1
                if direction > 0:
                    self._ensure_candidate((self.page + 1) * self.page_size + self.selected_index)
                last_page = (len(self._all_candidates) - 1) // self.page_size
                target_page = min(last_page, max(0, self.page + direction))
                self._highlight = min(
                    len(self._all_candidates) - 1,
                    target_page * self.page_size + self.selected_index,
                )
            return self._result(True)
        return self._result(False)

    @classmethod
    def _validate_mode(cls, mode: str) -> None:
        if not isinstance(mode, str) or mode not in cls.MODES:
            raise ValueError("mode must be 'jyutping' or 'forgiving'")

    def _replace_buffer(self, raw: str) -> None:
        # Resolve before changing state so a lookup failure preserves the old
        # composition and its candidates for the caller to recover or cancel.
        loader = getattr(self.engine, "lookup_page", None)
        next_offset = None
        completion_truncated = False
        if raw and callable(loader):
            page = loader(raw, offset=0, page_size=self.page_size, mode=self.mode)
            candidates, next_offset, completion_truncated = self._validate_page(page, 0)
        else:
            candidates = tuple(self.engine.lookup(raw, limit=self.MAX_CANDIDATES, mode=self.mode))[:self.MAX_CANDIDATES] if raw else ()
        self._buffer = raw
        self._all_candidates = candidates
        self._next_offset = next_offset
        self._completion_truncated = completion_truncated
        self._highlight = 0

    def _validate_page(self, page, offset: int) -> tuple[tuple[Candidate, ...], int | None, bool]:
        candidates = tuple(page.candidates)
        next_offset = page.next_offset
        completion_truncated = getattr(page, "completion_truncated", False)
        if not isinstance(completion_truncated, bool):
            raise ValueError("Engine returned invalid completion metadata")
        if page.offset != offset or len(candidates) > self.page_size:
            raise ValueError("Engine returned an invalid candidate page")
        if next_offset is not None and (
            isinstance(next_offset, bool) or not isinstance(next_offset, int)
            or not candidates or next_offset != offset + len(candidates)
        ):
            raise ValueError("Engine returned a nonprogressing candidate page")
        return candidates, next_offset, completion_truncated

    def _ensure_candidate(self, index: int) -> None:
        """Fetch only when navigation needs another page; failures retain state."""
        if index < len(self._all_candidates) or self._next_offset is None:
            return
        loader = getattr(self.engine, "lookup_page", None)
        if not callable(loader):
            raise ValueError("Engine no longer supports candidate paging")
        offset = self._next_offset
        page = loader(self._buffer, offset=offset, page_size=self.page_size, mode=self.mode)
        candidates, next_offset, completion_truncated = self._validate_page(page, offset)
        # The engine's pages must be a stable, deduplicated sequence. Treat
        # overlap as an error before changing the visible composition.
        seen = {candidate.text for candidate in self._all_candidates}
        if any(candidate.text in seen for candidate in candidates) or len({candidate.text for candidate in candidates}) != len(candidates):
            raise ValueError("Engine returned overlapping candidate pages")
        self._all_candidates += candidates
        self._next_offset = next_offset
        self._completion_truncated = completion_truncated

    def _select(self, absolute_index: int) -> SessionResult:
        candidate = self._all_candidates[absolute_index]
        if self.learn:
            recorder = getattr(self.engine, "record_selection", None)
            if callable(recorder):
                recorder(self._buffer, candidate, mode=self.mode)
        committed = candidate.text
        self.reset()
        return self._result(True, committed)

    def _result(self, handled: bool, committed: str = "") -> SessionResult:
        return SessionResult(
            handled=handled,
            committed=committed,
            preedit=self.buffer,
            candidates=self.candidates,
            selected_index=self.selected_index,
            page=self.page,
            has_more=self.has_more,
            completion_truncated=self.completion_truncated,
        )
