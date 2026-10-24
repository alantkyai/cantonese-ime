# Context experiment latency scope

This source audit describes what the existing timing and resource counters measure, and a plan for a separate latency experiment. It contains no new benchmark, native acceptance result or performance improvement claim. Context scoring remains an isolated, fresh-only experiment; model quality, capacity, latency and native integration require separate decisions.

## Existing evaluator timing

The inspected experimental evaluator is `.local/self-improvement/context-cycle3/evaluate_context_engine_v8.py`. Its `lookup` function starts `time.perf_counter()` at line 392, calls `lookup_page(page_size=90)` at line 394, and records `elapsed_ms` at line 416. Inside that interval it also:

- validates page and candidate metadata, readings, scores, uniqueness and input consumption;
- constructs the first-90 candidate pool, including hexadecimal floating-point scores;
- scans expected-text and text/reading ranks;
- computes candidate-pool, ordered-metadata and ordered-text hashes;
- constructs error details if the request raises.

Therefore, `elapsed_ms` is **lookup plus evaluator work**, not engine-only latency. It excludes process startup, module import and Engine construction. Fetching `last_context_diagnostics`, including the property's deep copy, starts after the timer at line 417. Later diagnostic validation, capacity classification and row serialization are also outside that interval. Diagnostics produced internally during lookup remain part of the timed lookup.

The older v6 evaluator has the same `lookup` timing function, at lines 364–399, with the timer at 366–390 and final diagnostic retrieval at 391. The local audit receipt records an AST comparison of the two functions without importing either evaluator.

V8 records constructor time separately at lines 546–552, after candidate-module import. It initializes the baseline, zero-weight and weighted engines in one process and queries those models in a fixed interleaving. Model parsing and filesystem caches can already be warm for a later engine. Its own qualification at lines 560–561 says these are diagnostic shared-process timings. Neither a maximum row time nor a difference between these arms establishes native latency or a measured speedup.

## Native transport and stale-work behavior

The client uses a [250 ms constant](../native/tsf/ipc.cpp#L14). [Exchange](../native/tsf/ipc.cpp#L111) establishes one deadline shared across pipe availability, connection, request write, response-length read and response-body read. It is not a separate 250 ms allowance for each operation. Identity checks and other ordinary function work also occur around those operations.

[Transfer](../native/tsf/ipc.cpp#L81) checks that deadline and bounds its overlapped-I/O wait by the remaining time. On timeout it calls `CancelIoEx`, then synchronously drains completion with `GetOverlappedResult(..., TRUE)` before releasing the operation and buffers. That lifetime requirement means 250 ms is not a hard upper bound on function return, key handling or OS cancellation completion.

The [key handler](../native/tsf/tsf.cpp#L541) calls `Backend::Lookup` synchronously. A failed initial request leaves the ordinary Latin key available to the host. During an existing composition, the frontend retains its documented literal Enter and Escape recovery; it does not commit a guessed candidate. Paging also makes a synchronous request at line 679.

The [broker worker](../native/backend/server.py#L325) reads a request, calls `dispatch` at line 336, then writes its response. Its five-second timeouts at lines 277 and 290 apply to pipe reads and writes, not Engine computation or Engine-lock acquisition. Sixteen pipe instances share one Engine. [Lookup takes the Engine lock](../cantonese_ime/engine.py#L483), so additional connected workers do not run conversions independently through that Engine.

A disconnected or timed-out client does not cancel an already-running `dispatch` or remove a worker waiting for the Engine lock. Such work can continue and delay newer requests. A later write discovers the broken connection. The current operation/resource limits bound specified algorithmic work and allocations; they are not wall-clock deadlines and do not time-bound filesystem, scheduling or lock delays.

The client [checks the echoed request ID](../native/tsf/ipc.cpp#L173). Each exchange uses its own pipe handle, so an abandoned response is not reused as the next exchange's reply. The [TSF generation check](../native/tsf/tsf.cpp#L571), advanced by `ClearState` at line 655, protects edit sessions from an old composition lifetime. It is not broker computation cancellation or a general asynchronous query-generation protocol. Any future asynchronous lookup design would need explicit ownership and current-request checks before publishing candidates.

Selection saving already runs on a separate native worker. Its queue is capped at 32 pending/in-flight notifications and each gets one transport attempt; those facts do not remove contention with lookup inside the broker's shared Engine. This audit does not change that behavior.

## Model and decoder hot path

The frozen corpus reader, `.local/self-improvement/corpus-cycle3-model/corpus_prior.py`, holds immutable packed bytes and small tuples rather than a dictionary of all bigram pairs. Relevant source anchors are:

| Anchor | Behavior |
| --- | --- |
| Lines 74–93 | Vocabulary ID lookup and packed-record binary search |
| Lines 95–107 | Two-stage conditional smoothing and clipped negative-log cost |
| Lines 110–118 | Actual size, bytes and SHA256 verification on every load |
| Lines 121–122 | Bounded cache of parsing for byte-identical payloads |

The fixed primary payload is 3,017,352 bytes and contains 327,403 lexical and 30,579 corpus bigram records. A newly requested pair performs vocabulary searches, the two packed-table searches, smoothing arithmetic and a logarithm. The model's one unknown bucket and initial `None` context must retain their exact semantics.

Model reading, parsing and the corpus wrapper's source-closure verification happen during construction. The wrapper also constructs the inherited engine with a separately pinned lexical compatibility model. Those checks are not repeated for every `lookup_page` call.

The lazy6 decoder's `.local/self-improvement/context-cycle3-lazy6/lazy_decoder.py`, lines 168–184, caches integer transition costs **within one decode**. A repeated pair in that decode is a hit; a new pair reserves a transition resource before calling the model. Internal word costs are likewise reused within a decode at lines 186–208. Changing the typed prefix starts another decode and can repeat provider calculations for the same pairs. Identical last-snapshot requests can instead bypass decoding; those hits must be distinguished in a benchmark.

Existing counters distinguish logical work, distinct pair requests, cache hits, allocated Context slots, slot reuse, hypotheses and byte generation. They do not directly measure model-provider CPU time, lock wait, cancellation drain or user-perceived key-to-candidate latency. `peak_frontier` is the maximum size of one heap, not aggregate process memory.

## Controlled measurement plan

Freeze the runner, engine, model, mapping, dictionary, request order and limits before measuring. Use public or newly synthetic input only. Finish concurrent quality jobs first, run one engine in one process per arm, and record Python/OS/machine details and background-load qualifications. Retain failures and slow requests rather than dropping them from percentiles.

1. **Cold process and first request.** Start a fresh child process for each arm. Report process-to-ready time, import/model verification and construction time, and first lookup separately. A fresh process does not prove a cold filesystem cache. Keep production garbage-collection behavior and disclose it.
2. **Warm changing queries.** Prewarm the frozen query set once, then measure several fixed rotating orders. Put wall-clock and process-CPU timers immediately around `lookup_page`, stopping before output validation, rank scans, hashes, diagnostic deep copies or file writes. Use page size 9 for the frontend-shaped request; measure page size 90 separately if useful. The engine may still calculate a larger internal candidate snapshot. Avoid adjacent identical `(normalized input, consumed length, mode)` requests; use an untimed sentinel when needed. Report cache hits separately, along with p50/p95/p99/maximum, sample count, errors, capacity statuses and input-length bands.
3. **Keystroke traces.** Replay every forward prefix, backspace and explicit repeat through one engine. Preserve prefix order rather than repeatedly timing only complete sentences. Separate intended snapshot hits from changing-input latency. Keep mode and tone/boundary controls, candidate metadata and capacity evidence. A serial engine trace measures service time; a later paced broker experiment must separately measure queueing and key-to-result behavior.
4. **Stress and transport follow-up.** Keep maximum-length and dense-ambiguity cases outside ordinary typing percentiles. A watchdog kill is not successful bounded completion. After an isolated engine experiment and separate authorization, test a project-local broker/client endpoint without replacing the active IME. Measure connection, queue/lock wait, dispatch, response transfer, deadline failure and cancellation-drain time. Delayed fake providers can test timeout recovery without claiming real language performance or TSF acceptance.

Existing release gates still apply. A benchmark must not silently widen limits, omit capacity failures or treat fast but incorrect candidates as acceptable. Native integration and the user's application/game check remain separate.

## Possible exact caching experiment

After model-quality review, an isolated candidate could add a bounded per-engine provider LRU storing the **exact final floating-point cost returned by the current provider**. Bind it to verified model, reader and source-policy identity; preserve initial-context and unknown-bucket semantics. A float cache need not depend on the ranking weight, but a cache of quantized weighted integers must also include weight, scale and quantization policy.

Do not rearrange smoothing arithmetic, replace division by multiplication, merge different model generations, or trust only a file path/mtime. Continue validating model bytes on load. Cache eviction must only cause exact recomputation. Keep decoder-local first-pair accounting, work and capacity checks unchanged even on provider-cache hits; record provider hits, misses, evictions and bounded allocation separately. Prove float-hex and ordered-candidate parity, including unknowns, initial contexts, tones, boundaries and cache eviction, before measuring any speed difference. No such cache is implemented or benchmarked by this audit.

The accompanying local source-pinned receipt records the inspected files, source hashes and line anchors. Experimental `.local` paths identify retained research artifacts, not shipped components. Existing reports, evaluator sources, model bytes and production code were not modified by this documentation work.
