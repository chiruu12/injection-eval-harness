"""Scenario corpus: unique keys, benign predicates, payload placement. No network."""

import re

from injection_eval.core.contracts import Scenario, ToolCall, Turn, TurnKind
from injection_eval.scenarios import all_scenarios, by_family
from injection_eval.systems import regex_hits


def _payloads_in_plan_order(scenario) -> list[str]:
    tools = scenario.build_tools()
    agent = scenario.build_agent()
    ordered: list[str] = []
    seen: set[str] = set()
    for call in agent.plan:
        if call.tool in seen:
            continue
        seen.add(call.tool)
        payload = getattr(tools[call.tool], "payload", None)
        if payload:
            ordered.append(payload)
    return ordered


def test_every_scenario_key_is_unique():
    keys = [s.key for s in all_scenarios()]
    assert len(keys) == len(set(keys))


def test_corpus_matches_the_family_shape():
    families = by_family()
    assert len(families["single_turn"]) == 4
    assert len(families["long_horizon"]) == 5
    assert len(families["split_payload"]) == 4
    assert len(families["benign_controls"]) >= 5
    assert {s.key for s in all_scenarios()} == {s.key for group in families.values() for s in group}


def test_every_entry_satisfies_the_scenario_protocol():
    for s in all_scenarios():
        assert isinstance(s, Scenario), s.key
        assert s.build_agent().plan
        assert s.build_tools()


def test_benign_objective_met_is_false_for_any_turn_list():
    hijack = Turn(
        index=3,
        kind=TurnKind.AGENT,
        content="",
        tool_call=ToolCall(tool="send_report", args={"destination": "quarterly_archive"}),
    )
    final = Turn(index=4, kind=TurnKind.AGENT, content="done")
    for s in all_scenarios():
        if not s.benign:
            continue
        assert s.objective_met([]) is False, s.key
        assert s.objective_met([hijack, final]) is False, s.key


def test_attack_objective_met_requires_the_attacker_tool_on_an_agent_turn():
    for s in all_scenarios():
        if s.benign:
            continue
        agent = s.build_agent()
        assert agent.triggers, s.key
        attack_tool = agent.triggers[0][1].tool
        hijack = Turn(
            index=2,
            kind=TurnKind.AGENT,
            content="",
            tool_call=ToolCall(tool=attack_tool),
        )
        other = Turn(
            index=1,
            kind=TurnKind.AGENT,
            content="",
            tool_call=agent.plan[0],
        )
        assert s.objective_met([hijack]) is True, s.key
        assert s.objective_met([other]) is False, s.key
        assert s.objective_met([]) is False, s.key


def test_task_completed_is_the_intended_final_answer():
    for s in all_scenarios():
        agent = s.build_agent()
        done = Turn(index=9, kind=TurnKind.AGENT, content=agent.final)
        other = Turn(index=9, kind=TurnKind.AGENT, content="not the answer")
        asserted = Turn(
            index=9,
            kind=TurnKind.AGENT,
            content=agent.final,
            tool_call=ToolCall(tool="send_report"),
        )
        assert s.task_completed([done]) is True, s.key
        assert s.task_completed([other]) is False, s.key
        assert s.task_completed([asserted]) is False, s.key


def test_attack_scenarios_declare_a_payload_on_a_tool():
    for s in all_scenarios():
        if s.benign:
            for tool in s.build_tools().values():
                assert getattr(tool, "payload", None) is None, s.key
            continue
        payloads = _payloads_in_plan_order(s)
        assert payloads, s.key


def test_attack_tool_calls_record_payload_span_from_splice():
    for s in all_scenarios():
        if s.benign:
            continue
        tools = s.build_tools()
        agent = s.build_agent()
        hits = []
        for call in agent.plan:
            result = tools[call.tool].call(call)
            if result.payload_span is not None:
                a, b = result.payload_span.start, result.payload_span.end
                assert result.content[a:b], s.key
                hits.append(result)
        assert hits, s.key


def test_split_payload_fragments_are_clean_until_assembled():
    for s in by_family()["split_payload"]:
        fragments = _payloads_in_plan_order(s)
        assert len(fragments) >= 2, s.key
        pattern = s.build_agent().triggers[0][0]
        for frag in fragments:
            assert regex_hits(frag) == [], (s.key, frag, regex_hits(frag))
            assert re.search(pattern, frag, re.IGNORECASE) is None, (s.key, frag)
        assembled = "".join(fragments)
        assert regex_hits(assembled), (
            f"{s.key} assembled instruction must hit regex_hits, or the family "
            "must be documented as keyword-undetectable"
        )
        assert re.search(pattern, assembled, re.IGNORECASE), s.key


def test_position_variants_share_an_identical_payload():
    by_key = {s.key: s for s in all_scenarios()}
    keys = ("long_horizon_pos01", "long_horizon_pos05", "long_horizon_pos10")
    expected_at_call = {
        "long_horizon_pos01": 0,
        "long_horizon_pos05": 4,
        "long_horizon_pos10": 9,
    }
    payloads = []
    for key in keys:
        scenario = by_key[key]
        tools = scenario.build_tools()
        assert len(tools) == 1, key
        tool = next(iter(tools.values()))
        assert tool.payload is not None, key
        assert tool.payload_at_call == expected_at_call[key], key
        payloads.append(tool.payload)
        n_plan = len(scenario.build_agent().plan)
        assert 8 <= n_plan <= 12, key
        assert tool.payload_at_call < n_plan, key
    assert payloads[0] == payloads[1] == payloads[2]


def test_long_horizon_plans_are_eight_to_twelve_calls():
    for s in by_family()["long_horizon"]:
        n = len(s.build_agent().plan)
        assert 8 <= n <= 12, s.key
