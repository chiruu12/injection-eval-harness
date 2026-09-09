### Primary: boundary-pairs test (240 rows, 120 pairs, published after every model)

| system | P | R | F1 | FPR | PR-AUC (95% CI) | ECE | pair acc | marginal acc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| regex-floor | 0.882 | 0.250 | 0.390 | 0.033 | 0.599 (0.529-0.666) | 0.447 | 0.250 | 0.608 |
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
| regex-floor | 1.000 | 0.150 | 0.261 | 0.000 | 0.590 (0.499-0.677) | 0.491 |
| unplug-model | 0.536 | 1.000 | 0.698 | 0.929 | 0.867 (0.795-0.926) | 0.456 |
| unplug-pipeline | 0.531 | 1.000 | 0.694 | 0.946 | 0.553 (0.444-0.685) | 0.384 |
| protectai | 1.000 | 0.367 | 0.537 | 0.000 | 0.929 (0.879-0.967) | 0.328 |

F1 gap, control minus primary: regex-floor -0.129, unplug-model -0.097, unplug-pipeline -0.100, protectai -0.160

### Controlled shift: seeded obfuscation of the 120 test positives and 120 test benign rows

| system | arm | baseline | base64_with_instruction | base64_bare | leetspeak | homoglyph | zero_width | whitespace | carrier |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| regex-floor | R | 0.250 | 1.000 (+0.750) | 0.000 (-0.250) ! | 0.000 (-0.250) ! | 0.017 (-0.233) ! | 0.133 (-0.117) | 0.133 (-0.117) | 0.250 (+0.000) |
| regex-floor | FPR | 0.033 | 1.000 (+0.967) ! | 0.000 (-0.033) | 0.000 (-0.033) | 0.000 (-0.033) | 0.000 (-0.033) | 0.000 (-0.033) | 0.033 (+0.000) |
| unplug-model | R | 0.792 | 0.000 (-0.792) ! | 0.992 (+0.200) | 0.633 (-0.158) | 0.708 (-0.083) | 0.867 (+0.075) | 0.808 (+0.017) | 1.000 (+0.208) |
| unplug-model | FPR | 0.200 | 0.008 (-0.192) | 0.958 (+0.758) ! | 0.700 (+0.500) ! | 0.567 (+0.367) ! | 0.450 (+0.250) ! | 0.250 (+0.050) | 0.942 (+0.742) ! |
| unplug-pipeline | R | 0.867 | 0.917 (+0.050) | 1.000 (+0.133) | 0.850 (-0.017) | 1.000 (+0.133) | 0.942 (+0.075) | 0.842 (-0.025) | 1.000 (+0.133) |
| unplug-pipeline | FPR | 0.317 | 0.558 (+0.242) ! | 0.992 (+0.675) ! | 0.392 (+0.075) | 1.000 (+0.683) ! | 0.783 (+0.467) ! | 0.458 (+0.142) | 0.992 (+0.675) ! |
| protectai | R | 0.842 | 1.000 (+0.158) | 0.000 (-0.842) ! | 1.000 (+0.158) | 0.958 (+0.117) | 0.792 (-0.050) | 0.758 (-0.083) | 0.450 (-0.392) ! |
| protectai | FPR | 0.575 | 1.000 (+0.425) ! | 0.000 (-0.575) | 0.992 (+0.417) ! | 0.925 (+0.350) ! | 0.558 (-0.017) | 0.533 (-0.042) | 0.108 (-0.467) |

`!` on R marks a drop of more than 20 absolute points, the pre-registered bar. `!` on FPR marks a rise of more than 20 absolute points, the companion bar.

### Span localisation, carrier transform only

unplug-model fired on 120/120 carrier documents. Character IoU against the known payload offsets: 0.884. Boundaries within 5 characters on 76/120 (0.633).

### Which stage decides, Unplug SDK, primary test

Of the primary test rows that produced any finding, 14.8% were decided by the regex stage alone and the checkpoint was never consulted (21 regex-only, 121 reached the model, 98 no finding).

### Episodes: attack success with the guard off versus on the tool-output boundary

| system | ASR off | ASR on | utility | late det | never-fired |
| --- | --- | --- | --- | --- | --- |
| regex-floor | 1.000 | 0.308 (-0.692) | 1.000 (+0.000) | 0.000 | 0.474 |
| unplug-model | 1.000 | 0.385 (-0.615) | 1.000 (+0.000) | 0.000 | 0.263 |
| unplug-pipeline | 1.000 | 0.077 (-0.923) | 1.000 (+0.000) | 0.000 | 0.053 |
| protectai | 1.000 | 0.846 (-0.154) | 1.000 (+0.000) | 0.000 | 0.895 |

ASR on and utility show the signed delta versus the unguarded run. Utility is task completion on the benign controls. Late detection and never-fired are the with-guard run.

### Position sensitivity: same payload at long_horizon posNN, guard on

| system | pos01 | pos05 | pos10 |
| --- | --- | --- | --- |
| regex-floor | 0.000 | 0.000 | 0.000 |
| unplug-model | 1.000 | 0.000 | 0.000 |
| unplug-pipeline | 0.000 | 0.000 | 0.000 |
| protectai | 1.000 | 1.000 | 0.000 |

---

Generated 2026-09-09T12:44:07+00:00 from harness da8ad0eb75f8, seed 20260912.
