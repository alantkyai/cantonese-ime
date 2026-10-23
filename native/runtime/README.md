# Per-user native IME runtime

`control.py` manages the Python conversion broker for an explicitly selected runtime bundle. `Start-Runtime.ps1` is a thin start wrapper. Neither file registers an IME, changes the Windows input selector, writes a Run key, creates a scheduled task, or enables login startup. The TSF DLL currently connects to an already-running broker; it does not launch one itself.

The bundle keeps this layout:

```text
runtime-config.json
cantonese_ime/*.py
data/generated/lexicon.sqlite3
data/generated/lexicon.manifest.json
data/mappings/{syllables,spellings,build.manifest}.json
native/CantoneseIME.dll
native/backend/server.py
native/runtime/{control.py,Start-Runtime.ps1,README.md}
```

The existing external AMD64 Python is a runtime dependency. It is recorded by absolute executable path, version, process bitness and executable SHA256; the interpreter, standard library and Python DLLs are not copied into the bundle. The executable hash does not attest the complete external Python installation. The portable C++ compiler and build sources are unnecessary for conversion at runtime.

After assembling the bundle, generate its config with the existing interpreter. This reads its version/bitness and writes the requested config; it does not start the broker:

```powershell
python native/runtime/control.py configure --install-root '<bundle-root>' --python '<existing-x64-python.exe>' --config '<bundle-root>/runtime-config.json'
```

`install_root` is `.` when the config is at the bundle root, so the complete bundle can be copied to its selected install directory. The external Python path remains absolute. Configuration refuses to overwrite a runtime input. Before configuring, review that the bundle contains the intended dictionary, sources and license notices; generating hashes is not source approval or linguistic review.

Local learning is enabled in a newly configured runtime. Its default store is `%LOCALAPPDATA%\CantoneseIME\learning.json`, resolved when the broker is started by the actual user, shared across that user's sessions and retained on broker restart. The config does not capture a staging account's SID or Local AppData path. The mutable store is separate from the pinned bundle. `configure --disable-learning` selects conversion-only mode. For an isolated smoke test, add `configure --learning-file '<absolute-test-file>'`; that explicit path is saved in config and passed to the broker, without creating or changing the file during configuration. Runtime inputs/control files cannot be used as the learning target. Changing the learning setting or path changes the runtime fingerprint and requires restarting the owned broker.

Only a successful candidate-selection notification can save memory. Ordinary lookup, literal Enter and cancellation do not save it. Memory includes the exact input, selected text and reading, lifetime count and adaptive weight; it stays local and is never written to diagnostic logs. Weights adapt among choices for the same complete input and mode, so a long phrase preference does not change a shorter input's preference. Previously selected composed phrases remain available for that exact complete input. Corrupt startup memory is preserved and conversion continues with learning unavailable. An unwritable or later-corrupt store causes a generic save failure while lookup continues; it is not silently reset. Repairing such a file requires explicit user action/restart. See `docs/ENGINE.md` for schema 1 compatibility, adaptive decay and limits.

The remaining commands accept `--config <absolute-config-path>`:

```powershell
python native/runtime/control.py verify --config '<bundle-root>/runtime-config.json'
python native/runtime/control.py start --config '<bundle-root>/runtime-config.json'
python native/runtime/control.py status --config '<bundle-root>/runtime-config.json'
python native/runtime/control.py stop --config '<bundle-root>/runtime-config.json'
python native/runtime/control.py print-login-command --config '<bundle-root>/runtime-config.json'
```

`verify` and `start` check the selected dictionary SHA256 against both the config and its source/build manifest. They verify pinned runtime files and AMD64 PE headers for Python and the IME DLL. These checks detect changes relative to the selected local config; they do not authenticate an attacker-edited config, replace source-license review, or approve pronunciation labels. Starting a different build requires stopping the old one first. Configuration and runtime verification do not import dictionary data or train ranking.

State is under `%LOCALAPPDATA%\CantoneseIME\Runtime\<SID>\session-<id>`, independent of the install directory. It contains `ownership.json`, `backend-ready.json`, `stop.json` when requested, `backend.jsonl`, and per-launch stdout/stderr logs. The pipe remains `\\.\pipe\CantoneseIME-<SID>-<session>`, compatible with the TSF client. Logs and state do not contain input, candidates, document contents or learning data. Logs are not currently rotated; they can be removed after the broker is stopped.

A current-user/session named mutex serializes control commands. Startup records a fresh UUID and the process's creation time, image path, token SID and session. Readiness must match that launch, dictionary and backend source; the controller also opens the actual pipe and checks its server PID. Status/stop hold a process handle while comparing its identity, so PID reuse cannot redirect shutdown to a successor process. An unknown broker using the same pipe is reported rather than adopted or terminated. Stop writes only the matching UUID/PID request and waits on the verified process handle. A timeout retains ownership and never forcibly terminates another process.

The backend checks an optional `--stop-file` every 100ms; only a request matching both `--runtime-instance` and its own PID triggers its existing orderly shutdown. Waiting pipe operations are cancelled/drained, workers are joined, and the engine closes afterward. A stop cannot interrupt conversion already executing in the engine. Omitting both options preserves the manual broker's lifecycle. Normal ready-file cleanup also matches the launch nonce.

If the broker has exited, a subsequent start can remove its stale ownership record. If the controller itself crashes between spawning a process and saving ownership, or ownership data is manually removed while a broker lives, the pipe is treated as unmanaged. Investigate that process using the original launch evidence; the controller deliberately does not guess ownership from a PID or command-line substring. There is no watchdog or automatic crash restart in this prototype.

`print-login-command` prints a hidden-window PowerShell start command only. An operator can enable that command at login as a separate explicit installation action. Until login startup or a later on-demand bootstrap is enabled, the user must explicitly start the broker before using the registered IME in an ordinary application. This source change alone does not establish persistent registration, installed-layout operation, or login reliability.

`tests/test_native_runtime.py` and `tests/test_native_backend.py` use synthetic packages and mocked processes/APIs. They test integrity checks, ownership, stale PID handling and nonce-scoped shutdown without launching a broker or changing Windows. Real installed-layout IPC and application typing require separate runtime evidence.
