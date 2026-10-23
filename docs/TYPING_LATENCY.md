# Changing-input latency

## Current distinct-composition run

The [current run](typing-latency-distinct-composition.json), captured on
22 October 2026 at 19:19 Hong Kong time, uses engine
`c2b67530f0fa42f14841f37e56369f776d023e4f63f67a4b92ad5085707e4d92`.
Its report SHA-256 is
`f7f323c0c3baaa6dbdb84d1dcea4d0a584065a72d4538f25c32df3b9e0afce97`.
The dictionary, 40-seed corpus, harness and phase methodology are unchanged
from the original run below; all before/after fingerprints matched and there
were zero errors. Project heavy benchmarks were paused during this capture.

| Phase | Earlier `dd9e6c46` p95 ms | Current `c2b67530` p95 ms | Current maximum ms |
| --- | ---: | ---: | ---: |
| Session first page, all 711 key events | 14.630 | 11.337 | 97.666 |
| Session changing keys, later 474 events | 14.521 | 10.597 | 94.844 |
| Backend limit 9, all 870 prefixes | 15.905 | 9.985 | 251.657 |
| Backend limit 9, later 580 prefixes | 15.563 | 9.804 | 84.318 |
| Backend limit 90, all 870 prefixes | 12.507 | 10.054 | 84.608 |
| Backend limit 90, later 580 prefixes | 12.603 | 9.905 | 84.608 |
| Identical full-query snapshot hits, 800 samples | 0.0103 | 0.0116 | 0.0283 |

Current Engine construction had median 2,171.928 ms across four instances.
The changing-query distributions were lower in this run, but these are two
sequential captures, not randomized paired measurements establishing a causal
speedup. Tails remain: `fai` took 251.657 ms in backend limit 9, and `la` took
97.666 ms in Session. The limited workload's warm p95 remains below the initial
20 ms target; it does not establish a hard bound or the 50 ms native target.

The refreshed [long-input check](long-input-coverage.json) preserves the
publication change caused by more distinct composed candidates. Among 666
unchanged scenarios, exact stored pairs were previously found 335 times within
90 candidates. Now 95 are within 90 and 240 appear at ranks 91–92 through
public paging. Exact-pair accessibility is unchanged for every scenario: zero
lost or gained targets. All 666 scenarios still reach their target text; 331
have another winning reading rather than the exact stored pair. Across the
222 entries, 187 have some exact-pair route and all have a text route. Full
over-cap input remains unsupported; 263 literal over-cap probes returned no
candidates. These are source-derived reachability checks, not human ranking
or pronunciation judgments.

The refreshed [mapping exercise](mapping-behavior-coverage.json) passes all
1,440 exported relations, 282 collisions, 10 numeric controls and the
257-homophone pagination fixture over 15,484 lookup scenarios. Both `m` prefix
capacity tails remain explicit: 38 visible candidates in forgiving mode and
37 in strict mode before a request requires refinement. Neither report hides
later-page targets or treats a bounded completion tail as full exhaustion.

Byte-exact preceding reports and the unit log are preserved under
[before-distinct-composition](baselines/before-distinct-composition/snapshot.manifest.json),
including the original latency JSON. The old module remains at
`.local/composition-search-baseline/engine.py`; its hash is `dd9e6c46…`.
No runtime or dictionary edits were made by these checks.

## Original baseline

The [saved run](typing-latency.json) measures the existing 40 development
seeds through changing input prefixes, with a separate Session replay of the
35 letter/apostrophe cases. Five numeric-tone cases remain in backend tests
but are excluded from Session, where digits select candidates. This is an
offline reference-engine measurement, not native Windows latency or held-out
typing accuracy.

Captured 22 October 2026 at 19:08 Hong Kong time, with learning disabled:

- Dictionary: `4353328cb17f8c8f8cc5d78730e34c3aa26c6c8ea7d1a4f4a8f91fee5d900a6e`.
- Engine: `dd9e6c46a702a945098b0a1c4c8dc54fb9c82e1aeb763430897b207ea4157d7e`.
- Seed corpus: `0d705ac210278c498269397173c942863b8fdbb265a9f6d7b1328925395300ed`.
- Harness: `dae78c53cfefb03bfb7e0eed2a5b68aadd15b10c63852eafdc9be3cec53386a1`.
- Report: `b1c2f7e58b1d8467ba850c97664d6b7b64dc5ee04b61ac435fbcf6eedf6071cf`.

All before/after source, corpus and dictionary fingerprints matched; no
exceptions or Session-state assertion failures occurred.

| Timed phase | Samples | Median ms | p95 ms | Maximum ms |
| --- | ---: | ---: | ---: | ---: |
| Engine construction, separate from queries | 4 | 2,124.797 | 2,225.369 | 2,225.369 |
| Session key event through available first page, all three passes | 711 | 4.278 | 14.630 | 90.314 |
| Session changing keys, later two passes | 474 | 4.039 | 14.521 | 90.314 |
| Backend changing prefixes, limit 9, all three passes | 870 | 4.022 | 15.905 | 271.210 |
| Backend changing prefixes, limit 9, later two passes | 580 | 4.062 | 15.563 | 116.186 |
| Backend changing prefixes, limit 90, all three passes | 870 | 3.491 | 12.507 | 90.295 |
| Backend changing prefixes, limit 90, later two passes | 580 | 3.491 | 12.603 | 90.295 |
| Identical full-input ranked-snapshot hits, after explicit priming | 800 | 0.0041 | 0.0103 | 0.2176 |

The changing-input phases use a fresh Engine each, replay corpus order three
times and keep that Engine alive within the phase. A new prefix is queried
after every character; no changing-phase call repeated the immediately prior
input/mode. Later passes reuse lower-level caches while still changing the
ranked query. The first corpus pass is not a claim of a cold cache: earlier
cases can already share prefixes.

Backend limits 9 and 90 run in separate phases so one cannot reuse the other's
ranked snapshot. Their phase order, process caches and machine scheduling
differ; the lower observed limit-90 time does not establish that requesting
90 candidates is faster. Engine construction is measured in the same process;
module caches and filesystem state are not a fresh-process/cold-disk test.

Session time ends when `handle_key` returns its preedit and visible first
page, including Session validation/state assembly. It includes 24 events with
no candidates; those are retained in the distribution. There are no timed
commits, paging selections, rendering, host edit sessions, IPC or artificial
typing delays. The identical-query phase explicitly primes each query outside
its repeated-hit timers and must not be presented as changing-key latency.

The report retains every prefix/key sample, per-case summaries and the 20
slowest samples per phase. Examples of observed tails are `lei` in the first
backend-limit-9 pass (271.210 ms), `dimgaai` in its next pass (116.186 ms),
and `ngoshuengsikch` in the second Session pass (90.314 ms, zero candidates).
These are elapsed observations; this run does not attribute the stalls to
the decoder, garbage collection, I/O or OS scheduling.

Observed later-pass p95 values are below the plan's initial 20 ms conversion
target on this limited seed workload. The retained stalls prevent any
hard-bound claim, and the separate 50 ms native candidate-update target remains
untested. Startup remains about 2.1 seconds. Neither this small corpus nor
identical-query caching establishes general responsiveness.

Run [the harness](../tools/check_typing_latency.py) when other project
benchmarks are idle:

```powershell
python tools/check_typing_latency.py
```

Before comparing an engine change, preserve this baseline and choose a new
report path, for example `--output docs/typing-latency-next.json`. Keep the same
corpus, pass count and measurement method; inspect per-input tails as well as
aggregate p95. A changed source hash makes this a historical baseline, not
current evidence for the new engine. No external corpus labels were fitted or
added to the dictionary for these measurements.
