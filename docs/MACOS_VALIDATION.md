# macOS native IME validation

Status: **source port implemented; native macOS acceptance pending**
(`source_port_implemented_native_pending`). The current
working host is Windows. Portable Python tests and source review cannot establish
Swift compilation, InputMethodKit registration, application typing, signing,
Gatekeeper acceptance or installer behavior on a Mac. Windows IME evidence is
separate and does not satisfy these checks.

The verified [source/build kit](../dist/CantoneseIME-1.0.0-macos/CantoneseIME-1.0.0-macos-source.zip)
contains the native frontend, shared engine, offline dictionary, official
universal2 Python build input, native test harness and app/PKG builder.
Its SHA256 is `86fa866a2ef3b71b565ed9b9e4c88e42265dd8618e890dd19753f1563985550b`.
The artifact is a source ZIP. Native app/PKG compilation and typing validation
remain pending. [Machine-readable status](macos-port-validation.json) records
the exact artifact and evidence.

## Native design and primary requirements

Apple's InputMethodKit provides the client communication, input-controller and
candidate APIs; its conversion engine may use another language. Each input
session has its own controller, so marked text and pending results must remain
associated with the correct session.
[Apple framework documentation](https://developer.apple.com/documentation/inputmethodkit)

The bundle must identify its background application, unique connection and
Objective-C-visible controller class consistently. Apple's server initializer
documents `LSBackgroundOnly`, `InputMethodConnectionName`,
`InputMethodServerControllerClass`, icon and character-repertoire metadata.
Matching property-list strings alone do not prove that Swift classes resolve at
runtime.
[Apple IMKServer initializer](https://developer.apple.com/documentation/inputmethodkit/imkserver/init%28name%3Abundleidentifier%3A%29)

The frontend must choose a supported event-handling approach and end a
composition when requested by the client. Commit and cancellation need explicit
state transitions so a delayed lookup cannot reinsert text or apply another
session's candidate.
[Apple IMKServerInput](https://developer.apple.com/documentation/inputmethodkit/imkserverinput)

Project review policy: keep the native frontend thin, use a private subprocess
for the offline engine, and make all text-client/candidate updates on the main
thread. Match each asynchronous result to request ID, process instance,
controller/client identity and composition generation. A process failure should
clear obsolete results and offer a recoverable next request.

The implemented source uses one controller state per input session, a compact
numbered candidate panel, `粵`/`英` mode menus and a shared private engine process.
It requires Swift 5.10 or newer (Xcode 15.3+) for the checked main-actor boundary
with a macOS 13 deployment target. These are source/build contracts; successful
native compilation and callback execution have not been observed here.

## Private runtime, bundle and distribution

Python's official macOS distribution provides universal2 builds, but its normal
installer uses fixed global framework and command locations. A private runtime
must be assembled and checked as a relocatable dependency tree; copying only
the framework's executable is insufficient evidence. Keep the runtime's original
licenses and record its source, architecture and hashes.
[Python 3.13 macOS documentation](https://docs.python.org/3.13/using/mac.html)

Apple requires valid nested-code structure and signing from the inside outward.
Frameworks/dylibs belong in their bundle locations; Python scripts belong in
resources. Finish relocation, install-name edits and resources before signing.
Runtime logs, bytecode and personal learning must remain outside the signed
bundle. Verify dynamic dependencies with the actual Mac tools, not a filename
or an architecture label in JSON.
[Apple code-signing technical note](https://developer.apple.com/library/archive/technotes/tn2206/_index.html)

For a notarized direct-distribution release, app/binary signing uses Developer ID
Application and installer-package signing uses Developer ID Installer. Hardened
runtime, valid timestamps and the final notarization result need their own
evidence. Ad-hoc signing is a development result, not notarized distribution.
[Apple notarization requirements](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution?changes=_9),
[certificate roles](https://developer.apple.com/documentation/security/resolving-common-notarization-issues)

Submit with the supported workflow, retain the notary log, staple supported
deliverables and verify the stapled result. Do not write credentials into source
or a distributable. Final hashes must describe the post-signing/post-stapling
artifact because those operations change bytes.
[Apple custom notarization workflow](https://developer.apple.com/documentation/Security/customizing-the-notarization-workflow?changes=la_8%2Cla_8%2Cla_8%2Cla_8)

## Portable checks

The Windows-hosted [exact-source-kit private-process transport report](macos-evidence/2026-10-23/sourcekit-engine-transport.json)
records 34 passing dictionary cases, source pins and a successful learning-store
restart. Phrase and constituent preferences remained separate. It explicitly
records `platform: win32`, no InputMethodKit proof and no personal learning opened.
The bridge's 11 focused unit tests also passed. These exercise the Python side;
they do not execute the Swift frontend or Apple's private-runtime launcher.

The [independent packaging tests](../tests/test_macos_packaging.py) passed 13
fixture checks, including manifest pins, changed notices, unsafe paths, duplicate
paths, framework-payload identity, retained licenses, source-change detection and
source-ZIP contents. They invoke no Apple tool or installer. Mach-O architecture,
relocation, actual framework links and signing remain native checks below.
The [combined bridge and packaging run](macos-evidence/2026-10-23/portable-tests-final.json)
passed **24 portable tests**. Its source pins match the final source archive.
The authored
Swift wire/state checks are included for execution on the build Mac; their
presence is not a passing result.

- [x] Python Standard-I/O bridge exercises length-framed IME1 binary messages,
  strict UTF-8, request identities, limits, candidate paging, explicit capacity
  errors, EOF and malformed requests. Metadata JSON is separate from this transport.
- [x] Python lookup/selection tests exercise canonical readings and mode/raw
  keys, rejected selections and persistence failures.
- [x] Recorded transport learning uses an isolated fixture store; personal data
  was not used as a fixture.
- [x] Portable packaging fixtures reject traversal, stale pins and changed
  notices, retain upstream licenses, and distinguish source ZIPs from native PKGs.
- [ ] Native bundle checks reject outside-bundle links, missing dependencies and
  wrong architectures on the actual extracted universal2 runtime.
- [ ] Bundle metadata, class/connection names, resource names and executable
  paths agree, including case-sensitive filesystem behavior.

## Checks requiring a macOS build/test host

- [ ] Record Mac model/architecture, macOS version, Xcode/SDK, deployment target,
  compiler commands and source hashes. Compile the declared arm64/x86_64 slices.
- [ ] Verify every executable, framework and extension module's architectures
  and dynamic links; demonstrate private-Python startup without global Python,
  developer directories or an inherited shell environment.
- [ ] Produce a complete `.app` in the declared input-method installation
  location, with all resource and license hashes checked.
- [ ] Register/discover the source as the intended ordinary user; selection and
  menu activation do not change an unrelated default source without a user action.
- [ ] Demonstrate plain Yale/Jyutping input, 1–9 selection, Space/Enter commit,
  Escape cancellation, arrows/paging and Latin passthrough in ordinary apps.
- [ ] Demonstrate `粵`/`英` menu state, candidate placement, retina/multiple-screen
  geometry and mouse selection without unintended focus theft.
- [ ] Type rapidly, cancel, switch clients and deactivate while lookups are
  pending. Delayed results cannot change another client or revive marked text.
- [ ] Verify a commit happens once and selection learning is queued only for
  the committed candidate. Repeated keys and backend restarts cannot duplicate it.
- [ ] Verify password/secure-input behavior and application-specific limitations;
  no unsupported secure-field guarantee is inferred from ordinary-app tests.
- [ ] Kill or stall only a disposable test backend, verify bounded failure and
  recovery, and confirm no main-thread pipe read/write can hang the client.
- [ ] Restart the input method and confirm learning persists in the intended
  user's Application Support directory with no writes inside the app bundle.
- [ ] Test upgrade/cancel/reinstall/uninstall, active input-method instances,
  multiple users and sign-out/sign-in. Preserve learning and unrelated sources;
  never use a broad process-kill or root-level user-preference rewrite.
- [ ] Verify signed app and nested code, package signature, notary acceptance,
  stapled ticket and clean-machine Gatekeeper behavior for the final artifact.

No check is marked passed merely because a script was generated or a package
filename exists. Keep unsigned/development artifacts clearly distinguished from
a distributable signed/notarized release.
