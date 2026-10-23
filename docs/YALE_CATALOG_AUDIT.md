# Stored-vocabulary Yale retrieval audits

The current development catalog contains **776,335 text/reading pairs across
644,427 texts**, database SHA-256
`bd312406a15162556ac58a257ede1514ad40890c793b6f8fa05084fda2d6241a`.
It uses engine `088d6956…` and the `cantonese-yale-ascii-v3` mapping module
`d61d6e7a…`. Its final exhaustive catalog scan **passed**, alongside all 567
Python tests and 31 staged native x64 cases. All **503,708 compact Yale input
groups**, representing **776,335 stored pairs**, reached their required texts
through **503,925 public page calls**, with **zero missing target memberships**.
All four workers exited successfully; elapsed worker time was **51 minutes
1 second**. The frozen replay also passed, reverifying all **58 copied files**
and preserving the original checkpoints. See [the final aggregate](final-yale-catalog-coverage.json),
[frozen replay](../.local/yale-catalog/final-v3-frozen-runtime/replay-validation.json),
[pre-install staged validation](yale-expanded-v3-ime-validation.json),
[current installed validation](yale-expanded-v3-installed-validation.json),
[development publication](final-development-publication.json) and
[actual worker records](../.local/yale-catalog/final-v3-full-run-sessions.json).

Two earlier finite-catalog proofs are complete and retained unchanged:

| Snapshot | Source pairs | Compact Yale inputs | Public page calls | Result |
| --- | ---: | ---: | ---: | --- |
| Original Yale, database `3fccc5bc…` | 736,570 | 488,219 | 488,436 | All required texts reached |
| Wordnet, database `d835b8c4…` | 739,128 | 490,313 | 490,530 | All required texts reached |
| Current v3, database `bd312406…` | 776,335 | 503,708 | 503,925 | All required texts reached |

The completed baseline check ran against database SHA-256
`3fccc5bcf45cbb676b8a1a51e2030d418803af64b3cd5c0ae7d67cf90a4711bb`,
engine `f45b0a29…`, mappings `72dc9c44…` and checker `f1fe6d43…`.
It covers 736,570 stored text/reading pairs, grouped into **488,219 distinct
compact plain-Yale inputs**. Status: **passed**. The reviewed aggregate verified
all four checkpoint chains and reached every required text through 488,436
public page calls, with zero missing target memberships. The workers ran in
parallel for 53 minutes 30 seconds. See [the aggregate](yale-catalog-coverage.json).

The [frozen runtime replay](../.local/yale-catalog/frozen-runtime/replay-validation.json)
also passes against its own byte-copied database, converter, engine and fixture.
Use that retained runtime to replay this baseline after subsequent dictionary
updates. The Wordnet [exhaustive aggregate](wordnet-yale-catalog-coverage.json)
also verified all four complete chains with zero missing memberships, in
54 minutes 1 second elapsed. Its independent
[frozen-runtime replay](../.local/yale-catalog/wordnet-frozen-runtime/replay-validation.json)
passes against the original checkpoint bytes. Neither historical result
automatically certifies the current v3 catalog.

The [checker](../tools/check_yale_catalog.py) derives inputs with the public
`yale_ascii` converter, retaining every required text for each input. It then
calls the actual public `Engine.lookup_page` API, continuing through pages until
all those texts are observed or an explicit end, error or capacity limit is
reached. It does not inspect the engine's private index as a substitute for
lookup. Learning is disabled. Duplicate tone/readings for the same text/input
are represented by one target text; the source-pair count remains separately
accounted. Rank and returned reading are saved per observed target.

V3 also accepts six KFCD-backed whole-syllable alternatives: `deeu`, `eeu`,
`meeu`, `peeu`, `seeu`, `jeeu`, alongside primary `ew`-family spellings. They do
not chain through spelling heuristics. `hm` and `hng` have explicit extension
provenance; `ngm` and `soei` remain Jyutping fallbacks. This checker exercises
primary compact inputs; its exhaustive claim does not extend to every
combination of alternate spellings, pronunciation correctness or formal Yale
coverage for all rare forms.

Every run binds dictionary, source, reference-fixture, catalog and shard hashes.
Only batches followed by a source-verified commit marker are trusted on resume.
Interrupted unverified tails require an explicit archived discard and recheck.
A single-writer lease prevents overlapping writers. A partial run, a completed
individual shard, an empty catalog, or a failure cannot claim complete catalog
verification. The checker has 14 focused tests, including real-engine retrieval,
later pages, corruption, interrupted resume and missing targets. The separate
[merger](../tools/merge_yale_catalog.py) has five focused tests for current complete
partitions, missing/duplicate shards, stale inputs, incomplete work and retained
shard leases during the combined verification. These
tests are tooling checks. The separate v3 product suite and native checks are
recorded in [the staged validation](yale-expanded-v3-ime-validation.json).
Earlier product suites remain attached to their own revision records.

The completed v3 run used four disjoint shards in a separate namespace.
Its checkpoints are sealed; do not launch another writer against them. These
are recorded commands, not instructions to start new workers on those paths.
A fresh audit needs a new namespace. The recorded shard indices were `0`
through `3`:

```powershell
python -u tools/check_yale_catalog.py --shards 4 --shard-index 0 `
  --checkpoint .local/yale-catalog/final-v3-full-shard-0.jsonl `
  --output .local/yale-catalog/final-v3-full-shard-0-summary.json `
  --progress-every 1000 --verify-every 1000
```

Use `--resume` only for a matching existing checkpoint. The checkpoint's source/catalog
identity must still match; a new dictionary or implementation needs a new run.
Exit code 0 means all targets in the selected partition were reached, 1 records
completed work with failures, and 2 means incomplete work. Shard success alone
is not a full-catalog claim. The completed run's merger validated all four
checkpoint chains against the current catalog with this recorded command:

```powershell
python tools/merge_yale_catalog.py `
  --checkpoint .local/yale-catalog/final-v3-full-shard-0.jsonl `
  --checkpoint .local/yale-catalog/final-v3-full-shard-1.jsonl `
  --checkpoint .local/yale-catalog/final-v3-full-shard-2.jsonl `
  --checkpoint .local/yale-catalog/final-v3-full-shard-3.jsonl `
  --output docs/final-yale-catalog-coverage.json
```

The completed v3 run retains
`.local/yale-catalog/final-v3-full-shard-{0,1,2,3}.jsonl` and corresponding
summary/stdout paths. Its aggregate is `docs/final-yale-catalog-coverage.json`.
Actual worker handles, starts and all four zero exits are recorded. Completion
was established from those exits and the verified aggregate, rather than a
timeout or an output file's existence. Its hash-pinned
`.local/yale-catalog/final-v3-frozen-runtime/` passed a fresh replay before
guarded inputs were released. Preserve both prior frozen runtimes and all old
checkpoints.

The [pilot summary](../.local/yale-catalog/pilot-summary.json) and checkpoint
remain separate from the full run. Both pilot latency spikes above 250 ms were
rechecked with a fresh engine: first full queries took 24.42 ms and 10.31 ms,
and all sequential typing prefixes completed below 32 ms in that finite probe.
See [the timing record](../.local/yale-catalog/latency-outliers.json). The spikes'
cause is unproven; these offline measurements do not establish a universal
native deadline guarantee.

This check concerns exact stored texts per compact input. It does not establish
that all Chinese vocabulary is present, that every source pronunciation is
correct, that every target ranks first, or that native Windows typing/UI checks
have passed. The catalog check itself does not install the IME or change personal
learning. A separate authorized update has now installed the r2 package
(`fde66d90…`), replacing the earlier numbered-choice package (`94c29cf8…`). All
86 installed payloads match, a fresh installed x64 DLL load passed, and the broker
is ready with learning enabled and personal-learning hashes unchanged. See
[installed validation](yale-expanded-v3-installed-validation.json). Reopen the
application and select Cantonese IME with Win+Space; user typing/UI QA remains
separate. The earlier canceled attempt remains in the
[historical canceled-stage record](yale-ime-validation.json).

Checkpoint inputs and target texts are source-derived data under the combined
[CC BY-SA 4.0 adaptation notice](../data/DATA_LICENSE.md). Retain the
[source attribution](../data/THIRD_PARTY_NOTICES.md) when sharing those reports.
