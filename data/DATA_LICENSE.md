# Dictionary data license

Full builds that select the **CC-Canto and CC-CEDICT Cantonese reading sources**
offer the combined transformed database adaptation under **Creative Commons
Attribution-ShareAlike 4.0 International**. The full applicable text is retained
in [licenses/CC-BY-SA-4.0.txt](licenses/CC-BY-SA-4.0.txt).

The original Pleco datasets remain **CC BY-SA 3.0 Unported**, with their full
original license, copyright headers and exact download-page declaration retained
in [the source snapshot](vendor/cc-canto/2017-02-02-and-2015-09-23/). Section
4(b)(ii) of that original license permits distributing an adaptation under a later
version with the same license elements. The modified database selects fields,
normalizes explicitly supplied readings, validates/quarantines records, deduplicates
pairs and combines them with other licensed source data. Those changes are this
project's responsibility. This notice does not claim to replace the original
component licenses or imply an upstream endorsement.

Additional selected CC-CEDICT written headwords and Yue Wiktionary readings
retain their own CC BY-SA 4.0 attribution and change notices. CC-CEDICT written
forms supply no Mandarin pronunciation to the Cantonese lookup data: their
additional readings are generated from separately recorded Cantonese character
inputs. Yue Wiktionary supplies only accepted explicit fields, with contributor
revision/history links retained. KFCD numeric-Yale spelling evidence retains its
original CC BY 3.0 component notice and attribution. The combined adaptation's
notice does not replace any original component license. Each build manifest
records which retained sources are actually selected.

Redistribute the data with this notice, the original source attribution and change
notices in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), and the applicable full
licenses. Modified database adaptations must preserve ShareAlike terms. The
original Rime/LSHK/TypeDuck and selected Cantonese Wordnet contributions retain
their CC BY 4.0 notices; words.hk's
selected public-domain wordlist declaration and the Unicode License V3 notice
remain applicable to their original components. Do not claim that a combined
CC-Canto-derived database is exclusively CC BY 4.0.

This is a license notice for data. Program code, the native IME and independent
tools are separate works; including a dictionary does not declare their code to
be CC licensed. No definitions are imported as lookup or review fields. The raw
licensed vendor files retain the complete source download, including definitions
where supplied, for provenance and reproducibility.

Historical database artifacts are identified by their own manifest/source hashes.
An older artifact that does not select CC-Canto is not retroactively changed by
this notice. Newly selected builds record `combined_data_license` in their
manifest and SQLite metadata.
