# Judge rubrics

The four judge checks of D-18. `scripts/judge_features.py` sends one feature file and every
`## judge-<name>` section below to a model, which returns findings as `line` and `reason`. A
judge flags only what its own section names. The form rules of GATE-22
(`tests/meta/test_feature_lint.py`) already cover step counts, keywords, tags, restricted
words and addresses: a judge does not repeat them.

Calibration: `tests/meta/judge-set/` holds feature files named `<judge>--defect-NN.feature`
(one seeded defect of that judge) and `clean-NN.feature` (no defect for any judge). A judge
turns blocking once it finds at least 26 of 30 seeded defects with at most 3 false findings on
30 clean files (D-18, S1): its `Status:` line then changes from `advisory` to `blocking`,
and the pull request that changes it shows the calibration output and `claude --version`. A
change to this file, to the model or to the claude CLI's major version reruns the calibration.

## judge-solution

Status: advisory

A step, name or description says how the system works instead of what someone gets: a request
count, a retry, a cache, a query, a parser, a library, a data structure or an internal call that
the outcome does not need.

Flag:
- "Then the fetch succeeds after 2 requests": the count is a mechanism.
- "When the refresher caches the calendar list".
- "Then the parser builds an interval tree of the events".

Leave alone:
- An outcome that is technical because the protocol is the product: "Then the server answers
  status 207" where the status is what the reader checks.
- A limit a reader outside the code can check: "Then the feed is at most one day old".

## judge-then

Status: advisory

A `Then` and the `And` or `But` after it state what someone outside the code can see or check:
the feed, a block in it, a file, an answer, a message, a recorded error. Flag a `Then` that names
internal state or says nothing checkable.

Flag:
- "Then the cache holds the entry".
- "Then the error is handled".
- "Then it works".

Leave alone:
- "Then the feed lists one busy block from 09:00 to 10:00".
- "Then the last error names the calendar 'work' as unreachable".

## judge-values

Status: advisory

`Given` steps and table cells name concrete values of the World, not categories. People appear by
role or a made-up number, never by name.

Flag:
- A category instead of a value: "Given an event in the past", "Given a long event", "Given some
  calendars".
- A placeholder: "foo", "test", "xyz", "lorem".
- A person's name: "Given Anna Weber shares her calendar".

Leave alone:
- "Given an event on 2026-10-25 from 09:00 to 10:00 UTC".
- "Given the owner's calendar 'work' holds 3 events".
- "Given calendar user 1042 shares a calendar".

## judge-brief

Status: advisory

The file stays brief and focused: one outcome per scenario, the field's own terms, Examples rows
that each add a case, and every scenario on the subject of its feature.

Flag:
- A scenario whose `Then` steps check two unrelated outcomes.
- Examples rows that repeat one case with other numbers.
- A scenario off the feature's subject, such as a feed-format scenario inside a fetch feature.
- One thing named two ways in the same file ("block" here, "slot" there).

Leave alone:
- `And` or `But` that refine the same outcome.
- Rows that each cover a distinct boundary.
