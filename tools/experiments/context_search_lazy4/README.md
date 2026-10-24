# Exact factored context search with shared outgoing streams

This isolated generic integer-search experiment is not enabled in the IME.
It imports no dictionary, language fixture or user history. The source snapshots
and checker are byte-identical to the hash-pinned versions used for the retained
proof. Keep `lazy_decoder.py` beside its pinned `mechanical_types.py` helper.

The [independent mechanical proof](../../../docs/self-improvement-cycle3-factored-mechanical.json) passes
9,312 exact comparisons over 388 graphs and
159,220 exhaustively scored complete paths. Both explicit cost tables
and subclasses whose callbacks hide their actual costs are checked. The proof
covers K=90, Unicode, duplicate text, segmentation and reading ties, dead paths,
and large equal-cost frontiers. It establishes the integer objective only on a
supplied retained graph; it does not recover discarded arcs or prove original
floating-point ordering, sentence quality or native latency.

The integer-zero specialization is retained. Nonzero search factors outgoing
arcs into groups by first emitted character, sharing group refinement and
sorted outgoing streams across incoming contexts. Each active written prefix
has a continuation through those streams. The search keeps the same exact
integer objective, distinct-text deduplication and greatest-reading tie rule.

All heap operations charge pushes/pops; shared group records, refined rows,
continuations and prefix/output nodes charge the existing hypothesis budget.
Scalar/outgoing records charge states. `peak_frontier` reports the largest
single live heap; it is not an aggregate memory bound. The separate hypothesis
counter bounds retained records. Schema 5 adds explicit group/refinement/stream
statistics without widening numerical limits.

The API remains `decode(arcs, end, model, k=9, incoming=None, limits=None)`.
Use nonnegative integer arc and transition costs and forward-only input arcs.
`Arc`, `CharacterModel`, `Limits` and `CapacityError` are exported by the module.
Capacity errors do not return a partial successful result. The seven resource
counters remain bounded independently from versioned search statistics; these
logical allocation/work limits do not measure Python RSS or caller-built graphs.

The [all-attempt real-graph diagnostic](../../../docs/self-improvement-cycle3-factored-diagnostic.json) retains
all 57 requests over the same 19 exposed inputs. Baseline and integer-zero control
complete 19/19; weighted context completes 16/19, with
3 unchanged 100,000-work failures. The strict runtime gate
fails. All 146 both-completed comparisons against earlier pilots
match full saved pools, float-hex scores, page metadata and target ranks exactly.
Against lazy3, zero-weight completion remains 19/19 and weighted completion rises from 11 to 16. No previously completed request is lost.
These are completion observations, not accuracy acceptance. The diagnostic
retains every failure and rank observation; there is no successful-subset quality
claim. No new corpus-model, development or protected-validation query is implied.

Every attempt retains `elapsed_ms` for a fresh full first-90 source query on
Windows, with initialization recorded separately. Some samples exceed 250 ms.
These are not native TSF or game measurements. Resource completion and latency
acceptance are separate gates, and the shared-process samples do not establish
a speedup.

Replay the synthetic proof from the repository root with a fresh output path:

```console
python -B -X utf8 tools/experiments/context_search_lazy4/check_exact_search.py --module tools/experiments/context_search_lazy4/lazy_decoder.py --expected-sha256 48e65a214b36914c1bb773140ed69239def12e92e7fda154872488b0f24d9a62 --output review-output/lazy4-mechanical-proof.json
```

The checker takes explicit paths, refuses to replace an output, and verifies
the decoder before and after execution. It requires only the Python standard
library. This command replays synthetic graphs; it does not replay the unpublished
local engine adapter or claim the protected fixture is public.

Frozen SHA256 pins:

| File | SHA256 |
| --- | --- |
| `lazy_decoder.py` | `48e65a214b36914c1bb773140ed69239def12e92e7fda154872488b0f24d9a62` |
| `mechanical_types.py` | `7c355e1ff76e501ec908c4c0493eefd87a2325affbdc010c2451c546a9bb96ac` |
| `check_exact_search.py` | `39b3894c7c892518bfad8aafb03ca68d33d3e9051fcaecfe053afcb0956ae2d3` |
| Mechanical proof JSON | `56642041a5d98c30f38da885bce965bf1c7ff740892f286b5f4be6ea7cdf6325` |
| Real-graph diagnostic JSON | `f8907bf2bd95542e75ec674899e0ab42fb66d0f648c1a5683e753b40b37610b5` |
