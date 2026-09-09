"""Episode tables follow the same markdown shape as the static ones."""

from injection_eval.report import episode_table, position_table

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
