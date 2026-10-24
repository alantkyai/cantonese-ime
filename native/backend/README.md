# Windows conversion broker

`server.py` serves the version1 length-framed protocol in `cantonese_ime/native_protocol.py`. The native client uses `native/tsf/ipc.cpp`. No broker is started by importing this module. Registration, installation, launcher changes and native execution are separate explicit actions.

The pipe name includes the current token SID and Windows session ID. Its DACL permits that user and SYSTEM; remote clients are rejected. The existing native client additionally checks the server process token SID. A session-specific name routes normal clients; it is not an independent authentication check against another process running as the same user.

The listener owns a fixed pool of 16 reusable pipe instances, one worker per instance. At capacity, additional clients encounter Windows' busy-pipe behavior; the broker never tries to allocate an invalid seventeenth instance. Workers retain no composition or learning state, and the shared engine serializes its own database operations.

All pipe operations are overlapped. Each operation owns its event, `OVERLAPPED` and ctypes buffers through completion. Shutdown or a 5-second transfer deadline cancels and drains pending I/O before releasing those objects. Waiting for a connection remains open-ended but checks shutdown every 100ms. Workers disconnect and reuse instances after malformed, broken or timed-out clients. Engine/pipe/security owners are released only after every worker joins. Engine calls already in progress finish before shutdown completes; I/O cancellation does not forcibly interrupt conversion code.

Ready metadata is published after pool startup and is removed on normal exit only if it still identifies this process and pipe. Abrupt process termination can leave a stale ready file; consumers must verify the PID/process and actual pipe, not treat file existence as liveness. Logs omit request text, candidates and document text. Dictionary, ready output and log paths must be distinct.

The optional runtime-controller pair `--runtime-instance <canonical-UUID> --stop-file <path>` enables graceful shutdown without process termination. The file must contain this launch's UUID and current PID; stale or malformed requests are ignored. Ready metadata includes the UUID, and normal ready-file cleanup matches it as well. Both options must be supplied together, and the stop file must be separate from the dictionary, ready file and log. The controller in `native/runtime/` keeps these files under Local AppData. No stop watcher is created for the original manual invocation without these options.

`--learning-file <path>` explicitly enables local selection memory. The normal runtime controller passes `%LOCALAPPDATA%\CantoneseIME\learning.json`, shared across user sessions; an isolated test config can pass another absolute path. `IML1` notifications are validated by the existing Engine against its current candidates and only acknowledged after a persistent save. `IME1` lookups do not save. The engine's atomic, process-locked schema 2 memory stores lifetime counts and adaptive full-input/mode preference weights and reads older schema 1 data. Selected composed phrases are retained for the same exact full input. No preceding-document context is collected. Unlike operational logs, this personal store contains the selected raw input/text/reading by design.

A corrupt/unreadable learning file during startup is preserved and triggers a conversion-only engine; the ready record distinguishes `learning_requested` from `learning_enabled`. A dictionary error still fails startup. A later save error produces a generic learning failure without breaking ordinary conversion or exposing paths/input in its message. No file is silently repaired, cleared or copied into the immutable runtime bundle. The learning file must be separate from the dictionary and broker control/log outputs.

The development broker enables `syllabic_m_as_ng`: whole-syllable typed `ng`
can also match canonical `m` in forgiving mode at cost 0.8, so existing compounds
such as those beginning with 唔 are eligible without a new dictionary reading.
This typing convention applies equally after a learning-file fallback. It
retains literal `ng` alternatives, numeric tones and strict Jyutping behavior.
Manual launches can disable it with `--no-syllabic-m-as-ng`; ready metadata
records the configured option under `input_conventions`. This change is not
included in the frozen 1.0.8 package.

Diagnostics use a separate writer and a queue capped at 4,096 records. Pipe workers never open or write the log file while reconnecting or serving a request. Queue overflow drops diagnostics rather than blocking input, with a `log_records_dropped` count emitted during normal shutdown. The writer drains before its file closes; abrupt termination can lose queued records. A logging failure is surfaced on normal shutdown. This keeps filesystem delays separate from pipe availability without claiming that a busy pipe will always become free before a particular client's timeout.

`tests/test_native_backend.py` uses mocked APIs and a fake engine exclusively. It covers full pool capacity, startup/cleanup failures, cancellation lifetime, saved Windows error codes, partial transfers, bad-client recovery and framing. Those tests establish Python control-flow behavior; they do not validate Win32 runtime ABI, pipe ACL enforcement, native activation or end-to-end typing.
