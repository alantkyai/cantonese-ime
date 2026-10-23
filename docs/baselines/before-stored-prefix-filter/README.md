# Evidence before stored-prefix completion filtering

These files preserve the reports captured before the completion search began
discarding committed syllable paths that cannot prefix a stored dictionary
reading. Each report's own capture metadata and hashes remain authoritative;
the copies were not rewritten to match the newer runtime.

The baseline engine SHA-256 is
`1dd3e62086d4c8491f3c7e4b81b50886dab3607878777b17269d4a90a9f25115`.
The updated engine SHA-256 is
`dd9e6c46a702a945098b0a1c4c8dc54fb9c82e1aeb763430897b207ea4157d7e`.
Both use dictionary SHA-256
`4353328cb17f8c8f8cc5d78730e34c3aa26c6c8ea7d1a4f4a8f91fee5d900a6e`.
The change narrows the completion search; it does not increase the 64-character
input cap or change the selected dictionary and spelling rules.

The saved [mapping report](mapping-behavior-coverage.json) and
[long-input report](long-input-coverage.json) can be compared with the
[current mapping report](../../mapping-behavior-coverage.json) and
[current long-input report](../../long-input-coverage.json). The long-input comparison measures
source-derived reachability; the mapping exercise uses synthetic text. Neither
is human pronunciation review or held-out user accuracy.

Paths recorded inside the frozen JSON retain their original project-root
meaning, including `.local/unit-tests.log`. The baseline log was copied here as
[unit-tests.log](unit-tests.log); use that sibling copy for the old report's
recorded log hash. The live project-root log may now belong to a later run.
Recorded runtime source paths identify the code at capture time and are expected
to differ from current source hashes after the fix.
