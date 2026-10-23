# CC-Canto source exceptions

`source_exceptions.json` is a generated ledger, not a human-approved correction
file. It preserves every rejected source row or text form, physical line number,
unmodified pronunciation field, source-record prefix and SHA256 of the full raw
line. English definitions are excluded from ledger fields; the full original
line is available in the pinned vendor text. The linked source lock identifies
the exact archives, extracted bytes, declarations, licenses and frozen parser
admission inventory.

Unknown syllables are un-attested against the frozen 878-base baseline, not
declared linguistically impossible. Codepoint/syllable mismatch can represent a
source error, unspoken punctuation, foreign text, or a genuine multisyllable
character such as `瓩`; the ledger does not automatically choose among these.
No y/j spelling, tone, punctuation or character repair has been inferred.

Use a separate human review file to propose exact source corrections and evidence;
do not edit generated fields or treat quarantine as an approval/rejection of a
linguistic reading. This ledger is source-derived work and must not be called an
independent held-out evaluation set. Running `tools/audit_cccanto_source.py`
regenerates it, so preserve any human notes separately.

The original CC-Canto data is CC BY-SA 3.0. This transformed ledger is included
under CC BY-SA 4.0 with attribution to Pleco and changes by this project. See
`data/DATA_LICENSE.md` and `data/THIRD_PARTY_NOTICES.md`.
