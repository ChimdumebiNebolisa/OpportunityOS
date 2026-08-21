# Eligibility, scoring, and queue rules

Eligibility is evaluated before score. A hard requirement that is false yields `ineligible`; a hard
requirement with missing, ambiguous, conflicted, or stale evidence yields `review_required`. Only all
true hard requirements yield `eligible`. Supported predicate operators are implemented in
`src/opportunityos/domain/decisions.py` and include equality, membership, comparisons, containment,
date bounds, and explicit unknown.

The default opportunity score is a weighted mean over nine 0–10 assessments:

| Dimension | Weight |
| --- | ---: |
| Strategic upside | 20 |
| Profile fit | 15 |
| Recognizable signal | 10 |
| Tangible output | 10 |
| Access/network | 10 |
| Financial support | 5 |
| Career optionality | 10 |
| Outcome plausibility | 10 |
| Preference alignment | 10 |

Effort subtracts a bounded penalty. Decision confidence combines evidence coverage and assessment
confidence. The default `apply` gate is score ≥ 75 and confidence ≥ 0.70; score ≥ 55 is `maybe`;
otherwise `pass`. Ineligible always passes, regardless of score. Hard unknown always requests review.

Queue priority combines net value, deadline urgency, readiness, available-time fit, and completion
ratio. Expired items are removed from the queue. Defaults and `ruleset_version` live in
`src/opportunityos/config/defaults.yaml`; changing them requires replay tests and a version bump.
