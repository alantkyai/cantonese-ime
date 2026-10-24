"""Isolated input-convention experiment; NOT production IME code.

Opt-in whole-syllable ng input for canonical m, cost0.8 matching existing optional pronunciation mergers. Does not rewrite the raw input,
published readings, weights, personal keys, or canonical ng alternatives.
"""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
MODULE_NAME = "cantonese_ime._self_improvement_engine_a4e2"
spec = importlib.util.spec_from_file_location(MODULE_NAME, HERE / "engine-a4e2-frozen.py")
frozen = importlib.util.module_from_spec(spec)
sys.modules[MODULE_NAME] = frozen
spec.loader.exec_module(frozen)
BaselineEngine = frozen.Engine


def coarse_nasal_key(value):
    # Preselection only: whole stored syllables are verified below. This may
    # overselect across boundaries; it cannot make a candidate match by itself.
    return frozen._yale_preselection_key(value).replace("ng", "m")


class NasalInputEngine(BaselineEngine):
    def __init__(self, *args, syllabic_m_as_ng=False, **kwargs):
        if not isinstance(syllabic_m_as_ng, bool):
            raise ValueError("syllabic_m_as_ng must be a boolean")
        self.syllabic_m_as_ng = syllabic_m_as_ng
        self._nasal_configured = False
        super().__init__(*args, **kwargs)

    def _effective_spelling_penalty(self, mode, spelling, base, penalty):
        if self.syllabic_m_as_ng and mode == "forgiving" and base == "m" and spelling == "ng":
            return 0.8
        return super()._effective_spelling_penalty(mode, spelling, base, penalty)

    def _configure_nasal_input(self):
        if self._nasal_configured or "m" not in self._yale_word_forms:
            return
        # Positive alias metadata preserves incomplete-alias discovery. Only
        # effective input-convention cost becomes zero in forgiving mode.
        self._insert("forgiving", "ng", "m", 0.8)
        self._yale_word_forms["m"] += (("ng", 0.8),)
        self._nasal_readings = {}
        for compact, readings in self._yale_readings.items():
            for reading, _ in readings:
                if "m" in reading.split():
                    self._nasal_readings.setdefault(coarse_nasal_key(compact), set()).add(reading)
        self._nasal_configured = True

    def _match_nasal_word(self, value, bases):
        # Retain one bit of provenance: the supplementary match must actually
        # consume ng as the complete canonical-m syllable. Proper m spellings
        # do not gain a new direct-word route merely by sharing this index.
        states = {(0, False): 0.0}
        for base in bases:
            following = {}
            for (start, used_alias), cost in states.items():
                for spelling, penalty in self._yale_word_forms[base]:
                    if not value.startswith(spelling, start):
                        continue
                    end = start + len(spelling)
                    if end < len(value) and value[end] == "'":
                        end += 1
                    used = used_alias or (base == "m" and spelling == "ng")
                    effective = self._effective_spelling_penalty("forgiving", spelling, base, penalty)
                    key = end, used
                    following[key] = min(following.get(key, math.inf), cost + effective)
            if not following:
                return None
            states = following
        return states.get((len(value), True))

    def _stored_yale_arcs(self, value):
        yield from super()._stored_yale_arcs(value)
        if not self.syllabic_m_as_ng or not self._nasal_configured:
            return
        compact = value.replace("'", "")
        if not compact.isalpha():
            return
        for reading in sorted(self._nasal_readings.get(coarse_nasal_key(compact), ())):
            penalty = self._match_nasal_word(value, reading.split())
            if penalty is not None:
                for entry in self._by_base(reading):
                    yield frozen._Arc(len(value), entry, penalty)

    def _rebuild_span_learning(self):
        if not self.syllabic_m_as_ng:
            return super()._rebuild_span_learning()
        self._configure_nasal_input()
        # Same schema, matching/reward caps and raw/mode keys as a4e2. The only
        # change is accepting the configured input convention for a learned m.
        self._learned_roots = {mode: frozen._LearnedNode() for mode in frozen.MODES}
        for (mode, raw, text, reading), weight in self._adaptive_weights.items():
            if weight <= 0:
                continue
            tokens = [frozen._READING.fullmatch(token) for token in reading.split()]
            forms = []
            for token in tokens:
                assert token is not None
                base, tone = token.groups()
                spellings = dict(frozen._spellings(base)) if mode == "forgiving" else {base: 0.0}
                if mode == "forgiving" and base == "m":
                    spellings["ng"] = 0.8
                forms.append(tuple((spelling + suffix, self._effective_spelling_penalty(mode, spelling, base, penalty))
                                   for spelling, penalty in spellings.items() for suffix in ("", tone)))
            penalty = frozen._match_yale_word(raw, tuple(forms))
            if penalty is None:
                continue
            node = self._learned_roots[mode]
            for letter in raw:
                node = node.children.setdefault(letter, frozen._LearnedNode())
            base = " ".join(token.group(1) for token in tokens)
            node.outputs.append((frozen._Entry(text, reading, base, 0.0), penalty,
                                 min(frozen._SPAN_LEARNING_MAX_REWARD, frozen._SPAN_LEARNING_REWARD * weight)))
        for root in self._learned_roots.values():
            pending = [root]
            while pending:
                node = pending.pop()
                node.outputs.sort(key=lambda item: (-item[2], item[0].text, item[0].reading))
                del node.outputs[frozen.MAX_CANDIDATES:]
                pending.extend(node.children.values())
