# Context scores and bounded personal preferences

This design note clarifies a future experiment. Context scoring is currently
disabled in production, and the context prototypes still reject learning files.
No personal history was inspected or used to derive this note.

## A valid additive objective

The inspected engine is SHA256
`02cff6ca13c2b59602a89b693ac8b35949a19e8d2e0ec12f02122491f3f3203f`.
Its learned-span calibration treats a preference as a bounded lexical discount.
For a retained arc, let `U` be unigram cost, `P` spelling penalty, and `R` the
already calibrated reward. The engine ensures `0 <= R <= U + 6P`.

Consequently the following objective is mathematically valid:

```text
path_cost = sum(U + 6P - R) + lambda * character_context_cost(whole_output)
```

The discounted lexical term stays nonnegative, as does the context term. The
existing reward can remain a fixed lexical-adaptation feature. Reanchoring that
reward against a context-scored span would define a different preference policy;
it is not required merely to make this additive search objective correct.
This supersedes that particular concern in the earlier fresh-only experiment
notes; their tests and failed measurements remain unchanged.

A personalized implementation must combine and clamp `U + 6P - R` once before
fixed-point quantization. Every search edge, suffix bound and cached scalar must
use that same discounted objective. It must bind the model and learning
generation to the cached search. Reusing an undiscounted bound can overestimate
remaining cost and incorrectly remove a preferred path.

This proves neither global dictionary coverage nor successful adaptation.
Per-span row bounds still affect the retained graph. The separate 10,000-point
exact-input preference is finite. In the current engine, a composition capacity
exception without a direct dictionary word is raised before the later exact
learned-memory restoration loop. Those behaviors need explicit tests and a
declared policy, rather than an assumption that exact memory always survives.

## Relevant upstream techniques

Rime combines entry weight with a grammar contribution in
[Grammar::Evaluate](https://github.com/rime/librime/blob/master/src/rime/gear/grammar.h).
Its [Poet implementation](https://github.com/rime/librime/blob/master/src/rime/gear/poet.cc)
keeps recent word context, uses a small beam for its grammar-enabled single
sentence strategy, and uses a beam proportional to the requested sentence count
for multiple results. These are bounded strategies, not a guarantee of an exact
global top K. This project currently investigates exact retained-graph search;
upstream beam sizes are not adopted as a new acceptance gate.

Source files were read through the GitHub connector on 24 October 2026 UTC:
`grammar.h` Git blob `ccd99007ff1c9c0c9bf0581e9ee593d38d7be812` and
`poet.cc` Git blob `963dd796d2e367e9fd1c0dbb6ba2a8b8da6bc33d`.
The additive-policy argument above follows from this project's own reward bound;
the upstream comparison is supporting design context, not quality evidence.

## Verification before enabling learning

Create short and heavy synthetic histories through the frozen baseline's actual
selection API, then clone their bytes for every model. Keep histories read-only
during comparisons. Check the zero-context control separately from the context
effect, including quantization differences. Preserve independent full-input and
shorter-input preferences, raw spelling keys, modes, tones, apostrophes,
selection validation, restart behavior and every capacity/fallback path.
Retain all rank losses and the existing quality and no-regression gates.

The native panel initially displays nine choices, while the current engine
computes its composed pool before slicing a page. If a future exact incremental
cursor is introduced, it must preserve the same global candidate order across
pages and invalidate on input, model or learning-generation changes. Allocation
limits per composition and work/latency limits per page advance must be stated
and measured separately. Paging is not permission to conceal discarded paths
or claim an exhausted result set after a capacity failure.
