# Exact context search with bounded scalar-slot reuse

This isolated integer-search decoder is not enabled in the IME. The decoder,
type helper and independent checker retain their exact frozen source bytes.
Keep the two source files together. They import no dictionary, language fixture
or user history.

The [mechanical proof](../../../docs/self-improvement-cycle3-slot-reuse-mechanical.json) passes 9,384 exact
comparisons over 392 graphs and 166,760 exhaustively scored complete paths.
It also retains 24 constructor-observed tiny-state cases: twelve runs complete
with exactly three allocated context objects and 80 in-place reuses; twelve
all-pinned two-slot runs fail before allocating a third object. This establishes
the declared integer retained-graph objective and observed allocation boundary,
not original floating-point order, dictionary coverage or language quality.

Eligible completed scalar-only slots and their lists are reused in place.
Recursive or outgoing-active slots stay pinned; a miss with every slot pinned
is an explicit capacity failure. `states` counts allocated slot objects, with
no decrement or hidden replacement allocation. All work remains charged and
the numerical caps are unchanged. Schema 7 exposes slot allocation, reuse,
current/peak pinning and computation counters. The exact integer-zero branch
keeps its position-only suffix tables and has zero slot-reuse statistics.

The [lexical pilot](../../../docs/self-improvement-cycle3-slot-reuse-diagnostic.json)
and [corpus pilot](../../../docs/self-improvement-cycle3-corpus-pilot-diagnostic.json)
each complete all 57 attempts on the same 19 exposed requests. All 255 earlier
completed lexical comparisons match exactly; all 38 baseline/zero model-control
comparisons match. The corpus model changes weighted costs, so every model
rank gain and loss is diagnostic rather than an equality or superiority claim.

The [full development evidence](../../../docs/self-improvement-cycle3-development-diagnostic.json)
retains aggregates and anonymous ranks from 1,968 attempts. New development
target text, readings, typed spellings and case mappings are not published.
Both models fail the original old-89 fresh gates: lexical first-page hits are
77/89 and corpus 73/89, below the required 90%; their longest-band counts are
23/30 and 20/30, below 80%. Passing the runtime-completion gate does not establish
accuracy, latency, native/game integration or release acceptance. Protected
validation and learning remain unqueried.

Historical `elapsed_ms` includes lookup and evaluator validation, target rank
scans and pool hashing. It is evaluation-row duration, not engine-only latency.
See the [timing scope audit](../../../docs/CONTEXT_LATENCY_SCOPE.md). Shared-process
samples and maxima do not establish a speedup or native latency acceptance.

Replay the synthetic proof only, from the repository root with a fresh output:

```console
python -B -X utf8 tools/experiments/context_search_lazy6/check_exact_search.py --module tools/experiments/context_search_lazy6/lazy_decoder.py --expected-sha256 a45761b275f02caef0c47a4f52297a0ae1bfb7ea277e6a40f6165b13dd17f3fe --output review-output/lazy6-mechanical-proof.json
```

The checker takes explicit paths, refuses to replace evidence, and checks the
decoder hash before and after execution. This package contains no production
adapter, model binary, new development labels or protected fixture.
