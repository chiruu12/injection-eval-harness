"""Episode tables follow the same markdown shape as the static ones."""

from injection_eval.report import episode_table, position_table, shift_table

BLOCK = {
    "regex-floor": {
        "with_guard": {
            "late_detection": {"late_detection_rate": 0.0, "n": 3},
            "detection_turns": {"never_fired_share": 0.25, "never_fired": 1, "n": 4},
            "position_sensitivity": {
                "pos01": {"attack_success_rate": 0.0, "n": 1},
                "pos05": {"attack_success_rate": 1.0, "n": 1},
                "pos10": {"attack_success_rate": 1.0, "n": 1},
            },
        },
        "without_guard": {},
        "delta": {
            "attack_success_rate_without_guard": 1.0,
            "attack_success_rate_with_guard": 0.5,
            "attack_success_delta": -0.5,
            "utility_rate_with_guard": 0.8333,
            "utility_delta": -0.1667,
        },
    }
}


def test_episode_table_matches_existing_pipe_style():
    text = episode_table(BLOCK)
    lines = text.splitlines()
    assert lines[0] == (
        "| system | ASR off | ASR on | utility | late det | never-fired |"
    )
    assert lines[1] == "| --- | --- | --- | --- | --- | --- |"
    assert lines[2] == (
        "| regex-floor | 1.000 | 0.500 (-0.500) | 0.833 (-0.167) | 0.000 | 0.250 |"
    )


def test_position_table_orders_pos_suffixes_numerically():
    text = position_table(BLOCK)
    lines = text.splitlines()
    assert lines[0] == "| system | pos01 | pos05 | pos10 |"
    assert lines[1] == "| --- | --- | --- | --- |"
    assert lines[2] == "| regex-floor | 0.000 | 1.000 | 1.000 |"


def test_episode_table_skips_systems_not_in_the_block():
    # ORDER has four systems; only regex-floor is present, so one data row.
    assert len(episode_table(BLOCK).splitlines()) == 3


SHIFT = {
    "regex-floor": {
        "baseline_recall": 1.0,
        "n_positives": 4,
        "baseline_fpr": 0.0,
        "n_benign": 4,
        "transforms": {
            "identity": {
                "recall": 1.0,
                "delta": 0.0,
                "recalled": 4,
                "n_positives": 4,
                "fails_robustness_bar": False,
                "fpr": 0.0,
                "fpr_delta": 0.0,
                "false_positives": 0,
                "n_benign": 4,
                "fails_fpr_bar": False,
            },
            "flag": {
                "recall": 1.0,
                "delta": 0.0,
                "recalled": 4,
                "n_positives": 4,
                "fails_robustness_bar": False,
                "fpr": 1.0,
                "fpr_delta": 1.0,
                "false_positives": 4,
                "n_benign": 4,
                "fails_fpr_bar": True,
            },
        },
    }
}


def test_shift_table_puts_recall_and_fpr_on_adjacent_rows():
    lines = shift_table(SHIFT).splitlines()
    assert lines[0] == "| system | arm | baseline | identity | flag |"
    assert lines[1] == "| --- | --- | --- | --- | --- |"
    assert lines[2] == (
        "| regex-floor | R | 1.000 | 1.000 (+0.000) | 1.000 (+0.000) |"
    )
    assert lines[3] == (
        "| regex-floor | FPR | 0.000 | 0.000 (+0.000) | 1.000 (+1.000) ! |"
    )


def test_shift_table_shows_a_skip_reason_instead_of_a_blank_cell():
    block = {
        "regex-floor": {
            "baseline_recall": 1.0,
            "n_positives": 1,
            "baseline_fpr": 0.0,
            "n_benign": 1,
            "transforms": {
                "broken": {
                    "recall": 1.0,
                    "delta": 0.0,
                    "fails_robustness_bar": False,
                    "fpr": None,
                    "fpr_delta": None,
                    "fails_fpr_bar": False,
                    "benign_skipped": "ValueError: not a payload (uid='b0')",
                }
            },
        }
    }
    lines = shift_table(block).splitlines()
    assert lines[3] == (
        "| regex-floor | FPR | 0.000 | ValueError: not a payload (uid='b0') |"
    )
