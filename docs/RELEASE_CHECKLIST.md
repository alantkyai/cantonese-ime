# Cantonese IME 1.0.5 verification checklist

The final distributable is built and its checks passed. The exact packaged
Hong Kong source migration previously succeeded twice on this Windows 10 x64
account. The 1.0.5 standard upgrade completed with exit code 0; its installed
files, registration and preserved preferences passed read-back checks. See
[current release notes](RELEASE_NOTES_1.0.5.md).

## Completed

- [x] Native AMD64 release DLL and standard single-EXE installer, without Preview branding.
- [x] Frozen setup, manifest, native build inputs, private runtime and 121 payload hashes.
- [x] Source licenses, full runtime/data notices and original attribution included.
- [x] Unsigned status and supported x64 desktop application scope disclosed.
- [x] Private interpreter import from outside the bundle; no developer Python required.
- [x] Prior core verification: 592 Python tests, zero failures/errors/skips;
  the validated engine and dictionary source pins remain unchanged.
- [x] 44 current lifecycle/package/builder tests, including two real Windows
  mapped-helper upgrade/rollback cases, both durable native rename intents,
  partial preparation failure and legacy-receipt compatibility.
- [x] Hong Kong migration retains its exact tested source bytes and earlier
  20-case coverage for tag normalization, concurrent changes and idempotence.
- [x] 34 native x64 real-dictionary cases, including learned `ng` compounds.
- [x] Isolated native selection learning persists after broker restart.
- [x] Fresh x64 DLL load and required exports, without invoking registration exports.
- [x] Native COM button mode/click notifications, sink ownership, teardown and eight icon sizes.
- [x] White outlined mode icons: 24 resources, 48 dark/white native renders.
- [x] Separate helper EXE branding reference captured from the production
  registration wrapper for both profiles, with 12 resource matches at six sizes,
  five negative cases and a missing-resource control.
- [x] Controlled same-Explorer probes reproduce the older loaded DLL's missing
  resource and demonstrate successful loading from a separate EXE container.
- [x] 18 registration argument/manifest guards and actual desktop read-only refresh preflight.
- [x] 84 exact no-learning comparisons against the prior engine, both input modes.
- [x] Initial bad `_pth` candidate preserved and rejected; corrected runtime policy rebuilt.
- [x] Synthetic preferences never copied into production learning.
- [x] Two ordinary-user live migration runs; independent installed read-back:
  Hong Kong enabled, old product English TIP disabled, English US retained.
- [x] Repeated migration leaves recorded language preferences and mutating
  helper-log timestamps unchanged. Zero setter calls are established by the
  reviewed guards and mocked fixtures rather than live API tracing.
- [x] Existing language properties, explicit UI/default overrides and culture
  match the full before snapshot.

## Final package installation

- [x] Standard 1.0.5 upgrade completes on this Windows 10 x64 PC with exit code 0.
- [x] All 121 installed 1.0.5 payload hashes, release name/icon metadata and source read back.
- [x] Original-user private engine reports ready after the 1.0.5 upgrade;
  personal learning hash, size and timestamp are unchanged during Setup.
- [x] All nine installed verification checks pass; English US, Array and the full
  language preferences match the fresh before snapshot.
- [x] Final installed helper icon loads in the same Explorer that still holds the
  old service image, using a controlled resource-load probe with balanced handles.
- [ ] User confirms the final installed 1.0.5 branding icon appears in the picker.

## Remaining acceptance

- [ ] User checks ordinary-app composition, selection, cancel, English pass-through and taskbar **粵 / 英** appearance.
- [ ] Clean Windows VM installation and Windows 11 machine test.
- [ ] Real sign-out/sign-in startup, repair/reinstall and end-to-end uninstall.
- [ ] Alternate administrator credentials and complete live failure/cancellation recovery matrix.
- [ ] 32-bit/ARM64 support: excluded rather than claimed.

Fixture/source checks do not establish these live results. The prior catalog and
typing proofs retain their original versions and hashes. Uninstall preserves
learning; exact startup values in unloaded user profiles may remain.
