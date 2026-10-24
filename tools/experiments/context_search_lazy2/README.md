# Exact context search with cost and text bounds

This isolated integer-only experiment addresses the large waiting frontier in
the [previous lazy decoder](../context_search_lazy/README.md). It is not enabled
in the IME. It imports no dictionary, language fixture or user history.

The [independent proof](../../../docs/self-improvement-cycle3-lexicographic-mechanical.json)
passes 4,644 exact comparisons across 387 graphs and 152,020 exhaustively scored
complete paths. It includes K=90, reading and segmentation ties, Unicode,
prefix strings and a graph with 100,000 equal-cost paths. The previous decoder
hits its unchanged hypothesis limit in 24 comparisons on the larger tied-path
graphs; this decoder completes all comparisons with the exact expected result.
This is a mechanical search result, not a sentence-accuracy or native-latency
claim.

The API remains `decode(arcs, end, model, k=9, incoming=None, limits=None)`;
`Arc`, `CharacterModel`, `Limits` and `CapacityError` come from this module.
Use nonnegative integer arc and transition costs. Every arc advances input.

Two bounds guide the search. First, the old context-free suffix cost `h0`
includes lexical and within-word character costs. A cached one-step bound is
`h1(position, previous) = min(edge_cost(previous, arc) + h0(arc.end))`.
Because incoming character costs are nonnegative, `h0 <= h1`; consequently
`h1(parent) <= edge + h1(child)`. Sorted arc baselines let this exact minimum
stop scanning once no remaining baseline can improve it.

Second, each input position retains its lexicographically least complete
written suffix, regardless of cost. The heap orders a path by its cost bound
and its prefix plus that minimum suffix. This pair is an admissible, consistent
lower bound in the final `(cost, text)` order, even when the two minima come
from different paths. After finding K distinct complete texts, the decoder
finishes only frontier bounds at most the Kth `(cost, text)` pair. All paths
tied on that exact pair are processed, preserving the greatest complete reading.
There is no prefix-reading dominance or beam pruning.

Numerical limits are unchanged. Their allocation units are explicit:

- `states` counts cached scalar h1 entries. Raw graph containers are separately
  bounded by the input-position limit.
- `hypotheses` counts prefix backpointers and complete candidates.
- `text_bytes` counts cumulative UTF-8 suffix, prefix and completion-key
  generation, reserved before concatenation; complete candidates reuse their
  charged prefix text. `reading_bytes` counts complete reading generation.
- `transitions` counts distinct cached character-pair evaluations. All requests,
  h1 scans, edge expansions and reconstruction also consume the separate
  100,000-unit work budget.

`Result.counters` contains seven resource counters; `Result.statistics` contains
typed search statistics, including the paired nullable cost/text cutoff.
Capacity errors return no partial successful result. These limits describe
logical allocation/work, not Python RSS or caller-owned graph construction.
Personalized ranking and native application acceptance remain outside this proof.

Replay from the repository root, choosing a new output file:

```console
python -B -X utf8 tools/experiments/context_search_lazy2/check_exact_search.py --module tools/experiments/context_search_lazy2/lazy_decoder.py --expected-sha256 3bfaba2290cb3b6ac873ba8c2982a2d9ae5d627610481bb73129d3bc9a949bd4 --output review-output/lexicographic-search-proof.json
```

The checker refuses to replace existing evidence and verifies the decoder
source before and after execution. The exact earlier `mechanical_types.py`
is retained as a helper; this experiment uses only the new `decode` function.
