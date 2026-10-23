# Collecting an independent typing corpus

The [empty template](heldout_cases.template.json) is for intended typing tasks
written independently of the dictionary sampler and development seeds. It is
not a benchmark yet. The evaluator deliberately rejects an empty case list.

Record phrases a Cantonese speaker actually wants to type, their natural input
spellings, and the intended output before consulting this engine's candidates.
Include casual phonetic spelling and formal Jyutping, colloquial expressions,
names, ambiguous sounds, tone entry, apostrophe boundaries and longer input.
Include difficult tasks and unsupported input, with their expected behavior
recorded separately from positive conversion targets. Do not fill this set by
copying dictionary rows or relabeling the generated review queue as independent.

For a positive conversion case, use the evaluator's existing fields:

```json
{
  "id": "unique-task-id",
  "input": "the speaker's actual spelling",
  "mode": "forgiving",
  "expected": ["the reviewed intended output"],
  "top_k": 9,
  "category": "colloquial"
}
```

The example above describes field shapes; it is not a valid Cantonese test case.
Accepted alternative outputs should be reviewed before scoring. Numeric tones
belong to the lookup API; the current typing Session uses digits for selection.
Negative/pass-through and key-sequence tasks need their own recorded expected
behavior rather than a fabricated Chinese target in `expected`.

Keep the author/reviewer, date, permission to use the contributed text, and any
source discovery or overlap notes. Agree on quality criteria before comparing
engine changes. Then freeze the reviewed file and record its SHA-256. Tuning on
failed cases makes them development cases; retain the results and collect a new
independent set for later quality claims. The CLI currently labels its coverage
as development evaluation and does not certify independent human review from
self-reported JSON metadata.

The initial plan proposed a reviewed 200-case core set and a later 500-plus-case
typing trial. Those are planning milestones, not data already collected here.
Native Windows trials remain deferred. No examples, speaker judgments or passing
scores have been invented in this template.
