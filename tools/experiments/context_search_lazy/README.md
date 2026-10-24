# Bounded lazy context search experiment

This integer-only A* decoder is an isolated search experiment. It is not enabled
in the IME and imports no dictionary, language fixture or learning profile.
The [independent proof](../../../docs/self-improvement-cycle3-lazy-mechanical.json)
records 3,456 exact comparisons over 384 small graphs, scoring 15,147 complete
paths with an independent exhaustive enumerator. It checks text deduplication,
reading ties, alternate word splits, dead paths, Unicode and zero-cost paths.
This establishes the declared objective on those graphs, not sentence quality
or native typing performance.

`lazy_decoder.decode(arcs, end, model, k=9, incoming=None)` accepts `Arc` and
`CharacterModel` from the same module. Costs must be nonnegative integers.
Each arc advances through input. The decoder removes paths with no complete
continuation and keeps incomplete paths as backpointers. Its lower bound uses
the cheapest remaining lexical and within-word character costs, omitting the
nonnegative incoming character cost. It therefore remains admissible and
consistent. Incoming context is charged when a path is expanded.

After finding K distinct complete texts, the search processes every remaining
path whose bound is at most the Kth cost. It then sorts by cost and text, keeping
the greatest reading among equal-cost paths for one text. It performs no beam
pruning or prefix-reading dominance. Character costs cover the whole output
independently of its word splitting.

Limits remain explicit, but their units differ from the earlier eager decoder:

- `states` counts input-position adjacency containers. Prefix backpointers and
  materialized complete candidates count toward `hypotheses`.
- `transitions` counts distinct cached character-pair model evaluations. Every
  request, cache hit, edge expansion and reconstruction also consumes the
  separate 100,000-unit work budget.
- Text and reading byte limits count cumulative complete-string materialization.
  Incomplete paths carry lengths and backpointers rather than copied strings.

`Result.counters` contains allocation/work resources with named `Limits` bounds.
`Result.statistics` separately reports search measurements, including a nullable
cutoff cost. A capacity exception returns no partial successful result. Bounds
describe logical allocations and work, not Python RSS, caller-owned graph
construction or an operating-system typing deadline. Floating-point legacy
ranking and personalized calibration are outside this proof.

Replay from the repository root, choosing a new output file:

```console
python -B -X utf8 tools/experiments/context_search_lazy/check_exact_search.py --module tools/experiments/context_search_lazy/lazy_decoder.py --expected-sha256 57ec11e84deda2b8be0c53069cf613549887713414d67b2bb3f20ed1fc50a707 --output review-output/lazy-search-proof.json
```

The checker refuses to replace evidence and verifies that the supplied decoder
source stays byte-identical. The helper `mechanical_types.py` retains the exact
earlier frozen definitions; only the lazy decoder's `decode` function is used
for this experiment.
