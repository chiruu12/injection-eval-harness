### Primary: boundary-pairs test (240 rows, 120 pairs, published after every model)

| system | P | R | F1 | FPR | PR-AUC (95% CI) | ECE | pair acc | marginal acc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| regex-floor | 1.000 | 0.025 | 0.049 | 0.000 | 0.599 (0.529-0.666) | 0.447 | 0.025 | 0.512 |
| unplug-model | 0.798 | 0.792 | 0.795 | 0.200 | 0.858 (0.799-0.910) | 0.195 | 0.600 | 0.796 |
| unplug-pipeline | 0.732 | 0.867 | 0.794 | 0.317 | 0.743 (0.654-0.829) | 0.191 | 0.550 | 0.775 |
| protectai | 0.594 | 0.842 | 0.697 | 0.575 | 0.733 (0.653-0.806) | 0.362 | 0.317 | 0.633 |

### Recall at a fixed false-positive rate, primary test

| system | R @ 0.5% FPR | R @ 1% FPR | R @ 5% FPR |
| --- | --- | --- | --- |
| regex-floor | 0.025 | 0.025 | 0.250 |
| unplug-model | 0.225 | 0.258 | 0.383 |
| unplug-pipeline | 0.075 | 0.075 | 0.117 |
| protectai | 0.000 | 0.000 | 0.250 |

### Control: deepset test (116 rows, predates every model, contamination-suspect)

| system | P | R | F1 | FPR | PR-AUC (95% CI) | ECE |
| --- | --- | --- | --- | --- | --- | --- |
| regex-floor | 0.000 | 0.000 | 0.000 | 0.000 | 0.590 (0.499-0.677) | 0.491 |
| unplug-model | 0.536 | 1.000 | 0.698 | 0.929 | 0.867 (0.795-0.926) | 0.456 |
| unplug-pipeline | 0.531 | 1.000 | 0.694 | 0.946 | 0.553 (0.444-0.685) | 0.384 |
| protectai | 1.000 | 0.367 | 0.537 | 0.000 | 0.929 (0.879-0.967) | 0.328 |

F1 gap, control minus primary: regex-floor -0.049, unplug-model -0.097, unplug-pipeline -0.100, protectai -0.160

### Controlled shift: seeded obfuscation of the 120 test positives

| system | baseline R | base64 | leetspeak | homoglyph | zero_width | whitespace | carrier |
| --- | --- | --- | --- | --- | --- | --- | --- |
| regex-floor | 0.025 | 0.000 (-0.025) | 0.000 (-0.025) | 0.000 (-0.025) | 0.000 (-0.025) | 0.000 (-0.025) | 0.025 (+0.000) |
| unplug-model | 0.792 | 0.000 (-0.792) ! | 0.633 (-0.158) | 0.708 (-0.083) | 0.867 (+0.075) | 0.808 (+0.017) | 1.000 (+0.208) |
| unplug-pipeline | 0.867 | 0.917 (+0.050) | 0.850 (-0.017) | 1.000 (+0.133) | 0.942 (+0.075) | 0.842 (-0.025) | 1.000 (+0.133) |
| protectai | 0.842 | 1.000 (+0.158) | 1.000 (+0.158) | 0.958 (+0.117) | 0.792 (-0.050) | 0.758 (-0.083) | 0.450 (-0.392) ! |

`!` marks a drop of more than 20 absolute points, the pre-registered bar.

### Span localisation, carrier transform only

unplug-model fired on 120/120 carrier documents. Character IoU against the known payload offsets: 0.884. Boundaries within 5 characters on 76/120 (0.633).

### Which stage decides, Unplug SDK, primary test

Of the primary test rows that produced any finding, 14.8% were decided by the regex stage alone and the checkpoint was never consulted (21 regex-only, 121 reached the model, 98 no finding).

---

Generated 2026-09-09T10:41:03+00:00 from harness ca06d2616787, seed 20260912.
