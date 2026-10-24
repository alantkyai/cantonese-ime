# Static integer-zero suffix merge and lazy exact scalar context suffix bounds

This isolated generic integer-search experiment is not enabled in the IME.
It imports no dictionary, language fixture or user history. The source snapshots
and checker are byte-identical to the hash-pinned versions used for the retained
proof. Keep `lazy_decoder.py` beside its pinned `mechanical_types.py` helper.

The [independent mechanical proof](../../../docs/self-improvement-cycle3-static-context-mechanical.json) passes
9,288 exact comparisons over 387 graphs and
152,020 exhaustively scored complete paths. Both explicit cost tables
and subclasses whose callbacks hide their actual costs are checked. The proof
covers K=90, Unicode, duplicate text, segmentation and reading ties, dead paths,
and large equal-cost frontiers. It establishes the integer objective only on a
supplied retained graph; it does not recover discarded arcs or prove original
floating-point ordering, sentence quality or native latency.

The exact integer-zero model uses a position-only distinct-text suffix heap
merge, avoiding character-context evaluation. That specialization requires the
exact `CharacterModel` type with an empty table and integer-zero default;
subclasses with hidden callback costs continue through the context search.

The nonzero arm uses exact lazy scalar suffix costs indexed by input position
and incoming character. It retains lexicographic `(cost, text)` cutoff and
processes all relevant reading ties. No beam or prefix-reading dominance is
introduced. Scalar-cache entries and strings remain charged under the original
state and byte limits.

The API remains `decode(arcs, end, model, k=9, incoming=None, limits=None)`.
Use nonnegative integer arc and transition costs and forward-only input arcs.
`Arc`, `CharacterModel`, `Limits` and `CapacityError` are exported by the module.
Capacity errors do not return a partial successful result. The seven resource
counters remain bounded independently from versioned search statistics; these
logical allocation/work limits do not measure Python RSS or caller-built graphs.

The [all-attempt real-graph diagnostic](../../../docs/self-improvement-cycle3-static-context-diagnostic.json) retains
all 57 requests over the same 19 exposed inputs. Baseline and integer-zero control
complete 19/19; weighted context completes 11/19, with
8 unchanged 100,000-work failures. The strict runtime gate
fails. All 97 both-completed comparisons against earlier pilots
match full saved pools, float-hex scores, page metadata and target ranks exactly.
Against lazy2, zero-weight completion rises from 11 to 19 and weighted completion from 8 to 11. No previously completed request is lost.
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
python -B -X utf8 tools/experiments/context_search_lazy3/check_exact_search.py --module tools/experiments/context_search_lazy3/lazy_decoder.py --expected-sha256 997f1dc91882435360c0cbb5a15e5c86f72024637b48ea952e9155a8edec3541 --output review-output/lazy3-mechanical-proof.json
```

The checker takes explicit paths, refuses to replace an output, and verifies
the decoder before and after execution. It requires only the Python standard
library. This command replays synthetic graphs; it does not replay the unpublished
local engine adapter or claim the protected fixture is public.

Frozen SHA256 pins:

| File | SHA256 |
| --- | --- |
| `lazy_decoder.py` | `997f1dc91882435360c0cbb5a15e5c86f72024637b48ea952e9155a8edec3541` |
| `mechanical_types.py` | `7c355e1ff76e501ec908c4c0493eefd87a2325affbdc010c2451c546a9bb96ac` |
| `check_exact_search.py` | `a8ad858a7398521772ac65e90546bf4d3b0258447deb46435128b38641be04f8` |
| Mechanical proof JSON | `de23cd24dd48ed002840abff9564f56c228e4695e9f51485272c0769bbe32191` |
| Real-graph diagnostic JSON | `58cf4298413a92bb4b5145295d37093b4bc6ca4e4e9f0abb93570fbfcafc9dbb` |
