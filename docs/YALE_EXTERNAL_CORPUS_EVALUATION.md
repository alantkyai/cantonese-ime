# Plain Yale external-corpus diagnostic

The 500 frozen HKCanCor cases were re-derived from their pinned source and kept
without filtering by dictionary membership. Each case was queried twice through
public `Engine.lookup`: once as compact plain Yale and once with apostrophes
between syllables. Learning was disabled, forgiving mode and Yale preference
were enabled, and the first 90 candidates were examined.

The source supplies Cantonese target texts and Jyutping annotations. The Yale
inputs were derived with the current converter, rather than independently
written by Yale users. Upstream overlap between the corpus and dictionary
sources is unresolved. These figures are a diagnostic, not clean held-out
accuracy or a natural typing acceptance test. No corpus readings or frequencies
were imported and no tuning was performed against these results.

| Cases and input | Requests | Text first | Text first 9 | Text first 90 | Exact text/reading first 90 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Word types, compact | 250 | 141 | 216 | 237 | 218 |
| Word types, apostrophes | 250 | 141 | 216 | 237 | 218 |
| Speech spans, compact | 250 | 31 | 92 | 123 | 97 |
| Speech spans, apostrophes | 250 | 32 | 94 | 124 | 98 |

All 1,000 requests returned candidates without exceptions or partial-input
consumption. Compact word-type text recall within the first 90 was 94.8%; whole
speech-span recall was 49.2%. The separation matters: retrieving a stored word
does not establish that arbitrary phrases will rank well.

Of the 13 compact word-type targets outside the first 90, none had its exact
annotated text/reading pair in the dictionary; two had the text with another
reading and 11 lacked the text. The 127 missed compact speech spans lacked the
whole target text and pair. Some cases contain names, spelling variants or
unresolved annotations. These observations describe the frozen evaluation;
they are not a list to import as training data.

The observed offline median was 9.000 ms, 95th percentile 29.564 ms and maximum
223.102 ms, while four catalog audit workers could be active. These are not
Windows IPC timings or a universal native deadline guarantee.

The evaluated dictionary is SHA-256
`d835b8c4487b90ef751c8c91f467b9245c8bd54ee5be8157531dd9530ac7667b`,
engine `f45b0a29693e613ba9dd0633be7ca67e905ad3bbca17b95fc01aac36df823d5f`,
and mappings
`3eaee728fc7355d466dee722e1ee4f67e508eb9c362fd92762b8d0531e5e99fe`.
All guarded source, fixture, implementation and dictionary hashes were unchanged
after scoring.

Full per-case results and provenance are in
[`yale-external-corpus-evaluation.json`](yale-external-corpus-evaluation.json).
The read-only runner is `.local/evaluate-yale-corpus.py`. Source attribution and
CC-BY-SA-4.0 terms remain in `eval/hkcancor.sources.lock.json`,
`data/DATA_LICENSE.md` and `data/THIRD_PARTY_NOTICES.md`.
