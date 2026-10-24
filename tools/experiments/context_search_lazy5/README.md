# Exact context search with shared ordered group minima

This generic integer-search experiment is not enabled in the IME. It imports
no dictionary, language fixture or user history. The decoder, type helper and
independent checker are byte-identical to the frozen mechanical proof inputs.
Keep `lazy_decoder.py` beside its pinned `mechanical_types.py` helper.

The [mechanical proof](../../../docs/self-improvement-cycle3-ordered-groups-mechanical.json) passes 9,360 exact
comparisons over 390 graphs and 166,440 exhaustively scored complete paths.
It covers explicit cost tables and subclasses with hidden callback costs,
K=90, Unicode, segmentation/reading ties, dead paths and large equal-cost
frontiers. New stress graphs exercise shared outgoing groups and scalar minima
whose order differs from their weaker context-free bounds. The proof applies
only to the declared integer objective on the supplied retained graph. It does
not recover discarded arcs or prove original floating-point ordering.

This revision retains the exact integer-zero suffix merge and factored
nonzero search from [lazy4](../context_search_lazy4/README.md). A shared stream
at each position orders groups by the exact `(minimum T, written lower bound)`
of their first realized arc. Incoming scalar search can stop when the next
actual minimum cannot improve its best cost; outgoing streams reuse the same
exact pair order as a lower bound. Groups are not ordered by an unrelated
context-free written suffix. The exact objective, text deduplication, greatest
complete-reading tie rule and numerical limits remain unchanged.

New stream controls and realized heap rows charge the existing hypothesis
budget; all heap work is counted. Schema 6 has the same seven resource counters
and 30 typed statistics. The four position-minimum statistics expose stream
counts, requests, cache hits and refinements, with declared bounds. They are
all zero in the exact static-zero arm. Resource units describe logical
allocation and work, not Python RSS or caller-owned graph construction.

The [all-attempt dictionary diagnostic](../../../docs/self-improvement-cycle3-ordered-groups-diagnostic.json)
retains all 57 attempts on the same 19 exposed inputs. Baseline and zero control
complete 19/19; weighted context completes 17/19. Two weighted requests hit the
unchanged 1,024-state limit, so the strict runtime gate fails. Weighted
completion rises from 16 to 17 against lazy4, with no earlier completion lost.
All 200 comparisons completed by both current and earlier pilots match full
saved pools, float-hex scores, pages and ranks exactly. These are completion
observations, not successful-subset accuracy or release acceptance.

Every attempt retains `elapsed_ms` for its fresh full first-90 source query on
Windows, with initialization separate. Shared-process timings and failed
requests do not establish a speedup or native TSF/game latency acceptance.
No corpus-model, broader development or protected-validation query follows
from this evidence package.

The API remains `decode(arcs, end, model, k=9, incoming=None, limits=None)`.
Use nonnegative integer arc and transition costs, forward-only arcs, and the
exported `Arc`, `CharacterModel` and `Limits` types. Capacity errors return no
partial successful result. This experiment does not contain the local engine
adapter or protected fixture.

Replay only the synthetic proof from the repository root, using a fresh output:

```console
python -B -X utf8 tools/experiments/context_search_lazy5/check_exact_search.py --module tools/experiments/context_search_lazy5/lazy_decoder.py --expected-sha256 4ca8c0d0bfa6718943262e4043cc8bda2b53861d99ec302f4d3c9ccc6f789d61 --output review-output/lazy5-mechanical-proof.json
```

The standard-library-only checker takes explicit paths, refuses to replace
existing evidence, and verifies the decoder before and after execution.

| File | Frozen SHA256 |
| --- | --- |
| `lazy_decoder.py` | `4ca8c0d0bfa6718943262e4043cc8bda2b53861d99ec302f4d3c9ccc6f789d61` |
| `mechanical_types.py` | `7c355e1ff76e501ec908c4c0493eefd87a2325affbdc010c2451c546a9bb96ac` |
| `check_exact_search.py` | `49298e2ffaaac3810f315c4081eeef4fedeb58a249f7205c63b74e05eef659e9` |
| Mechanical proof JSON | `de917cee8fabbd3cc26cb2469eb266a0e1986ab49a947ba1ca57938d4694663d` |
| All-attempt diagnostic JSON | `7c2d0b093990cf35eff80bf5369ea51102f6810fbb07d5cb995fa60605741d37` |
