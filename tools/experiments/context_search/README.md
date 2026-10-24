# Context-conditioned decoder: mechanical prototype

This directory is a synthetic search experiment. It imports no product engine,
dictionary, user history or quality fixture. It changes no production files.

`docs/self-improvement-cycle2-mechanical.json` records the guarded run: 13 tests pass, with 2,897 exact
exhaustive-oracle comparisons, including 320 deterministic random DAGs tested
with three incoming contexts and three K values (2,880 random comparisons).
The independent reviewer found one mutable-model contract gap; the final model
is frozen and the test explicitly rejects attribute reassignment. The report
pins the decoder, tests, runner and unchanged product engine/mapping files.

## What is proved

`context_decoder.decode(arcs, end, model, k=...)` returns the best K distinct
written texts **on its supplied retained lexical DAG**. The state is
`(input_position, incoming_character)`; `None` marks the beginning of input.
An arc's context cost includes every emitted character, both within a word and
across word boundaries. Therefore one output string has the same character
cost whichever word segmentation produced it.

For a fixed state and fixed outgoing arc, its emitted text, lexical cost,
character-transition cost and ending context are constant. Its suffix stream
comes from the child state with that actual ending context. Prepending the
same text preserves text order and distinctness, and adding a constant
preserves cost order. Thus a child suffix below its best K distinct texts
cannot enter its parent's best K. A heap merges the per-arc streams lazily.

Duplicates do not consume visible K. All paths with the same cost and text at
the cutoff are consumed before selecting the lexicographically greatest
reading, matching the product's existing text-dedup tie policy. Zero-cost arcs
are allowed because every arc must advance through input.

The tests score complete strings in an independent exhaustive enumerator,
without calling decoder state discovery, character consumption, heap merge,
path joining or its dedup implementation. Integer costs avoid floating-point
association ambiguity. Exact floating-point ordering is **not** proved.

## Why a context-free suffix reranker is insufficient

Two suffixes have lexical costs `a=1` and `b=2`. After the fixed prefix `x`,
character costs change them to `xa=5` and `xb=2`. A competing stream emits
`z=3`. A context-free suffix top-1 table discarded `b`, so reranking surviving
`xa` and `z` returns `z`. The context-conditioned algorithm returns `xb`.
Keeping the old sorted suffix stream but adding boundary costs only at heap
insertion has the same hidden-successor problem.

## Bounds and failure contract

The default experimental bounds are 257 input positions, 4,096 caller-supplied
arcs, 1,024 reachable context states, 32,768 character-transition evaluations,
32,768 generated hypotheses, 100,000 heap pushes and pops, 8 MiB of cumulative
generated UTF-8 written text and 16 MiB of generated UTF-8 readings. Output
strings are limited to 1,024 characters and readings to 8,192 characters;
K is at most 90. Model preparation is bounded to 131,072 supplied pairs.

These are finite **experimental** bounds, not native latency guarantees or
measured Python RSS. Caller-owned inputs have separate finite preparation
bounds. Reservations happen before state/transition publication, hypothesis
construction, output concatenation and heap insertion. Exceeding a bound
raises `CapacityError` with counters and returns no partial successful Result.
The tests exercise each resource at an exact successful boundary and one
below it, plus output-length failures before allocation. Model and results
are immutable once validated.

The proof does not recover arcs discarded by a phonetic frontier/row bound,
estimate an LM, establish language quality or authorize enabling context for
personalized profiles. It does not claim whole-process latency or native IME
readiness.

## Exact next Engine hook: fresh profiles only

A separate local subclass of a pinned Engine can override only
`_compose_sentences(arcs, size, *, work_limit=...)`. It must:

1. Require `learning_path is None` before calling the base constructor; reject
   any nonempty `_selections` or `_adaptive_weights` again at composition time.
   Override `record_selection` to raise. Keep one immutable context-model,
   model-hash, weight and fixed-point scale per Engine instance, so existing
   snapshot caching cannot reuse candidates under a changed model.
2. Traverse exactly the old reachable input-position graph using `arcs(pos)`.
   Skip root full-input arcs exactly as the original composition path does.
   Reserve its own retained-arc budget **before** appending converted arcs.
   Reject any nonzero `arc.learning_reward`; a learned profile is out of scope.
   Do not change dictionary discovery, tones, apostrophes, mode validation,
   input normalization, direct-word collection, prefix completion or paging.
3. Set the generic lexical cost to the original combined static arc objective:
   `max(0, self._log_total - log1p(weight)) + 6 * arc.penalty`.
   Supply a frozen licensed character model whose per-character costs are
   finite and nonnegative, including transitions inside each word. Its
   interpolation, clipping, weight and source exclusions must be declared
   before inspecting diagnostic outputs. Do not train it on evaluation text.
4. Prefer a declared fixed-point scale, such as 1,000,000 units per cost,
   rounding each lexical arc and character transition once. This yields the
   exact integer ordering tested here; it is a declared quantized objective,
   not bit-identical legacy floating-point arithmetic. An alpha-zero control
   should report any differences explicitly. Float costs are supported for
   experimentation but have ordinary association/ULP limitations.
5. Decode the supplied graph with K=90 and explicit limits. When converting a
   result back to `_Sentence`, put its **combined** cost (lexical plus weighted
   character cost, divided by the scale) in `.cost` and use `.penalty=0`.
   Otherwise the base decoder subtracts the spelling penalty twice. The
   flattened canonical reading can be placed in the one-element readings
   tuple; `.words` comes from the winning path. The public final reading stays
   the original space-separated canonical reading.
6. Translate a local capacity failure to `CompositionCapacityError` with its
   counters. Preserve the base decoder's explicit truncation/direct-word
   fallback behavior; never publish a partial composition as exhaustive.
   Preserve direct1000/1100 priority, exact full-input memory code and all
   public page semantics. This compose-only experiment changes composed
   ranking; it deliberately leaves stored direct-word ranking unchanged.

The context model can use a small immutable wrapper around the frozen packed
lexicon prior rather than materializing a dense character matrix. The wrapper
must perform a bounded lookup/formula per character; charge that work against
the transition counter. This prototype's finite explicit cost table is a
mechanical stand-in, not that production model implementation.

**Do not enable it for learned profiles yet.** Current transferred-learning
calibration uses same-span unigram/path anchors. Adding context afterwards
would compare rewards anchored under one objective with paths ranked under
another. A later personalized design needs context-conditioned anchors or a
separately justified bounded policy, while keeping all combined piece costs
nonnegative and exact full-input selection priority intact. A context state
must also be threaded through that calibration; merely letting this subclass
accept a learning file is unsafe. No such policy is tested here.

An incoming two-character state can later express trigrams with the same
fixed-prefix proof, but its reachable-state and memory expansion needs a new
bound and new mechanical tests before language experiments.

Run from the repository root with `python -B tools/experiments/context_search/run_mechanical_checks.py --output .local/context-search/new-run.json`. Choose a fresh output path; existing evidence is never overwritten. This command performs synthetic checks only.
