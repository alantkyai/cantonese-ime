# Composition search: independent synthetic analysis

The old forward beam loses outputs that rank within its own unigram objective. This is a search defect, separate from the quality of that language model. The current backward-search candidate fixes the tested cases without changing dictionary rows, weights, spelling rules or tone grammar.

The [machine-readable evidence](composition-search-analysis.json) binds the exact engine, mapping module and checker hashes used. Its baseline is engine `dd9e6c46a702a945098b0a1c4c8dc54fb9c82e1aeb763430897b207ea4157d7e`; the tested candidate is `c2b67530f0fa42f14841f37e56369f776d023e4f63f67a4b92ad5085707e4d92`. The checker opens only temporary, project-authored synthetic dictionaries. It does not open the selected live lexicon or the external HKCanCor corpus.

## Confirmed losses

Ten handcrafted fixtures cover canonical, explicitly toned, apostrophe-separated and forgiving inputs, duplicate pronunciations, lexical ties, direct-word priority and the retained-arc boundary. The baseline matches the exhaustive oracle in one fixture; the candidate matches all ten. Seven baseline cases omit at least one oracle top-nine output, and five choose a different pronunciation on an equal-score written-text tie.

| Fixture | Exhaustive result | Baseline result | Candidate result |
| --- | --- | --- | --- |
| Nine distinct `nei5` prefixes followed by `hou2` | 9 outputs | 8 | 9 |
| Prefix texts `A` through nine repeated `A`s, followed by text `B`, equal weights | Nine-`A` + `B` ranks first | Best output omitted | Correct first output |
| Six pronunciations each of `P` and `A`, plus lower-weight `Q` and `B` | 49 paths, 4 distinct outputs | Only `PA` | All 4 |
| Same duplicate paths with explicit `nei5hou2` | 4 outputs | 4 | 4 |
| Duplicate `P`/`Q` prefix pronunciations and lower-weight `R` | 3 distinct outputs | 2 | 3 |
| Eight distinct prefixes and eight distinct suffixes | 64 distinct outputs | 32 | 64 |
| 100 direct whole-input words plus 2 composed outputs | 100 direct, then 2 composed | Composed outputs absent | All 102 reachable through paging |

The duplicate-path case also exposes a reading tie error: the full graph's best `PA` reading is `nei6 hou6`, while the old 32-path final slice retained only enough duplicates to select `nei6 hou2`. Deduplicating written text after those path caps cannot recover the discarded paths.

The lexical example explains why simply raising the forward beam is weaker than changing its direction. Appending the same suffix can reverse the order of prefix-related strings: `A` sorts before `AA`, but `AAB` sorts before `AB`. Prepending one fixed arc to suffix strings preserves their lexical order.

## Bounded backward search

For each input position, keep the best 90 **distinct suffix output texts** on the retained dictionary-word arc graph. A fixed preceding arc adds the same cost to every child suffix, preserves written-text order, and maps distinct suffix texts to distinct full texts. A child suffix below the first 90 therefore already has 90 distinct outputs ahead of it through that same arc; it cannot enter the parent's first 90. Other arcs may supply better paths for those texts, but do not remove the texts themselves.

Merge each arc's ordered suffix list with a heap, advancing a stream only when its head is used. Deduplicate output text before the cap. Finish the equal-cost/equal-text group before publishing its winner, choosing the lexicographically greatest complete reading to match the public candidate deduplication rule. At input position zero, exclude an arc covering the entire input from this composition search: direct stored words have their own candidate branch and must not consume the composed-output budget before being filtered out.

The checker independently enumerates every complete path in 100 seeded small DAGs: 39,602 paths in total, up to 2,944 in one case. Both the independent lazy prototype and the current production search helper match their exhaustive top-90 text, reading and objective results in all 100 cases. These random DAGs deliberately include duplicate texts, prefix-related texts, variable arc lengths and cost ties. Binary-exact costs isolate the search algorithm from floating-point association.

The current helper uses a global 100,000 heap-pop guard and raises `CompositionCapacityError` rather than returning an incomplete pool when it is exhausted. Arc discovery and storage still have separate bounds. The prototype's low-budget control checks that exhaustion raises before returning a partial result.

## Scope and remaining limits

This result applies to the **retained acyclic arc graph**, not every path that might be composed from all dictionary rows. The decoder still limits matching rows and arcs to 90 per applicable group and retains 96 phonetic paths while discovering multi-syllable words. A separate synthetic control has 217 full-graph paths with two distinct outputs; the 90-arc preparation keeps only one output. The new search correctly returns the best result on that retained graph and cannot recover the other output from an arc that was never supplied to it.

The composed pool remains bounded at 90 distinct texts before the existing learning overlay. Learning is consequently not exhaustive over otherwise omitted composed paths. Stored direct matches and prefix completions remain separate branches. More composed outputs can move a lower-scored completion beyond the legacy `lookup(limit=90)` window; `lookup_page` can still reach it when it is present in the fixed candidate pool. Choosing 32 versus 90 composed outputs is a visible pool-size decision, independent of fixing duplicate-path loss.

The reference oracle uses `math.fsum` over arc costs; the runtime builds suffix costs in the opposite association from the old forward beam. Multiword floating-point scores may differ by an ulp. The handcrafted public-API comparisons allow score differences below `1e-9` and require exact text and reading order in those fixtures. The seeded DAGs use exactly representable costs and penalties.

A synthetic six-layer work probe has 180 arcs and analytically 729 million possible complete paths. The independent prototype returns 90 outputs after 480 heap pops, with at most 30 heap heads. Its single observed runtime is recorded in the JSON report, rather than treated as a stable performance estimate. It is neither a live-dictionary latency benchmark nor evidence about native Windows IME responsiveness.

No preferred spelling, pronunciation, real-language ranking quality or external-corpus improvement is established by these synthetic checks. They establish the narrower mechanical result that the tested search returns the best bounded set under its supplied additive objective and retained graph.

## Reproduction

Run the checker against the current engine:

```powershell
python tools/check_composition_search.py
```

The comparison report was produced with an exact private copy of the old engine at `.local/composition-search-baseline/engine.py`:

```powershell
python tools/check_composition_search.py --baseline-source .local/composition-search-baseline/engine.py
```

The selected dictionary is not needed. Runtime/checker file hashes are verified again before the report is written. The baseline source is a local experimental snapshot; the saved report records its full SHA-256 rather than relying on its filename as provenance.
