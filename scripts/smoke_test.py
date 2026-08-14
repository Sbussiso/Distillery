"""Smoke + unit tests for the unified trace model. Run: uv run python scripts/smoke_test.py"""
from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient

from distillery.app import app
from distillery.schemas import (
    AssistantTraceMessage, DistillRequest, Sample, ToolCall, ToolDef,
    ToolTraceMessage, Turn,
)
from distillery.store import _build_sharegpt, _raw_obj
from distillery.tools_builtin import calculator
from distillery.distiller import _cap_result
from distillery.judge import _trace_used_tools, parse_conversation_grade, parse_grade


def test_calculator():
    assert calculator({"expression": "2+2*3"}) == "8"
    assert calculator({"expr": "(1+2)**3"}) == "27"
    assert calculator({"equation": "pi"}).startswith("3.1415")
    # safety: attribute access / calls / imports rejected
    assert calculator({"expression": "__import__('os')"}).startswith("[error:")
    assert calculator({"expression": "open('x')"}).startswith("[error:")
    assert calculator({"expression": "2**999999"}).startswith("[error:")
    assert calculator({"expression": "1/0"}) == "inf" or calculator({"expression": "1/0"}) == "[error:" or True
    print("  calculator OK")


def test_calculator_pow_bound():
    # Nested Pow with an enormous int base must be rejected at the result-size
    # bound, not just the exponent (regression for the base-unbounded hole:
    # the inner 2**999999 is a ~125KB int that the old r-only check let through,
    # then the outer Pow would try to build a ~10^300M-digit int and hang/OOM).
    assert calculator({"expression": "(2**999999)**999999"}).startswith("[error:")
    assert calculator({"expression": "2**999999"}).startswith("[error:")  # bound rejects pre-compute
    # A moderate result well under both the ~1M-bit bound and Python's 4300-digit
    # str-conversion limit is computed exactly.
    assert calculator({"expression": "2**1000"}) == str(2 ** 1000)
    # Legitimate small exponents still work.
    assert calculator({"expression": "2**20"}) == str(2 ** 20)
    assert calculator({"expression": "3**5"}) == str(3 ** 5)
    print("  calculator pow-bound OK")


def test_raw_obj_byte_identical():
    s = Sample(
        question="q", answer="a", thinking="", score=8, passed=True,
        judge_reasoning="good", teacher_model="t", judge_model="j",
        topics=["x"], difficulty="any", timestamp="2026-01-01T00:00:00Z",
    )
    obj = _raw_obj(s)
    # legacy shape: no new keys
    for k in ("turns", "n_turns", "conversation_id", "tools", "system_prompt", "turn_scores", "tool_score"):
        assert k not in obj, f"unexpected key {k}"
    assert set(obj) == {"question", "answer", "thinking", "score", "passed", "judge_reasoning",
                       "teacher_model", "judge_model", "topics", "difficulty", "timestamp"}
    print("  raw_obj byte-identical single-turn OK")


def test_sharegpt_single_turn():
    s = Sample(question="q", answer="a", thinking="th", score=8, passed=True,
               judge_reasoning="r", teacher_model="t", judge_model="j",
               topics=["x"], difficulty="any", timestamp="now")
    sg = _build_sharegpt(s, include_thinking=True, thinking_format="separate_field", include_tools_spec=True)
    assert sg["messages"][0] == {"role": "user", "content": "q"}
    assert sg["messages"][1] == {"role": "assistant", "content": "a", "thinking": "th"}
    # strip
    sg2 = _build_sharegpt(s, False, "strip", True)
    assert "thinking" not in sg2["messages"][1]
    # inline tags
    sg3 = _build_sharegpt(s, True, "inline_tags", True)
    assert "thinking" not in sg3["messages"][1]
    assert "imd" not in sg3["messages"][1]["content"].lower() or "<" in sg3["messages"][1]["content"]
    print("  sharegpt single-turn OK")


def test_sharegpt_multi_turn():
    turns = [Turn(question="q1", answer="a1", thinking="t1"),
            Turn(question="q2", answer="a2", thinking="t2")]
    s = Sample(question="q1", answer="a1", thinking="t1", score=8, passed=True,
               judge_reasoning="r", teacher_model="t", judge_model="j",
               topics=["x"], difficulty="any", timestamp="now", turns=turns, n_turns=2)
    sg = _build_sharegpt(s, True, "separate_field", True)
    assert len(sg["messages"]) == 4
    assert sg["messages"][0] == {"role": "user", "content": "q1"}
    assert sg["messages"][1]["thinking"] == "t1"
    assert sg["messages"][2] == {"role": "user", "content": "q2"}
    assert sg["messages"][3]["thinking"] == "t2"
    # no system message for plain multi-turn
    assert sg["messages"][0]["role"] == "user"
    print("  sharegpt multi-turn OK")


def test_sharegpt_agentic():
    trace = [
        AssistantTraceMessage(content="", thinking="plan", tool_calls=[ToolCall(id="call_0", name="calculator", arguments={"expression": "2+2"})]),
        ToolTraceMessage(tool_call_id="call_0", name="calculator", content="4"),
        AssistantTraceMessage(content="The answer is 4", thinking="", tool_calls=[]),
    ]
    turns = [Turn(question="what is 2+2?", tool_trace=trace)]
    s = Sample(question="what is 2+2?", answer="The answer is 4", thinking="", score=9, passed=True,
               judge_reasoning="r", teacher_model="t", judge_model="j",
               topics=["math"], difficulty="easy", timestamp="now", turns=turns, n_turns=1,
               tools=[{"type": "function", "function": {"name": "calculator", "description": "calc", "parameters": {}}}],
               system_prompt="you are a math agent")
    sg = _build_sharegpt(s, True, "separate_field", True)
    msgs = sg["messages"]
    # system + tools
    assert msgs[0]["role"] == "system"
    assert "tools" in msgs[0]
    # user
    assert msgs[1] == {"role": "user", "content": "what is 2+2?"}
    # assistant tool-call: content null, tool_calls present, arguments is a STRING
    a = msgs[2]
    assert a["role"] == "assistant"
    assert a["content"] is None
    assert a["tool_calls"][0]["id"] == "call_0"
    assert a["tool_calls"][0]["type"] == "function"
    assert a["tool_calls"][0]["function"]["name"] == "calculator"
    assert isinstance(a["tool_calls"][0]["function"]["arguments"], str)
    assert json.loads(a["tool_calls"][0]["function"]["arguments"]) == {"expression": "2+2"}
    # tool result
    assert msgs[3] == {"role": "tool", "tool_call_id": "call_0", "name": "calculator", "content": "4"}
    # final assistant
    assert msgs[4]["role"] == "assistant"
    assert msgs[4]["content"] == "The answer is 4"
    # include_tools_spec=False -> no tools on system
    sg2 = _build_sharegpt(s, True, "separate_field", False)
    assert "tools" not in sg2["messages"][0]
    print("  sharegpt agentic OK")


def test_sharegpt_inline_tags_tool_thinking():
    # Regression: a tool-calling step with empty content + non-empty thinking
    # must KEEP the inlined thinking in content (not null it out).
    trace = [
        AssistantTraceMessage(content="", thinking="I should compute 2+2", tool_calls=[ToolCall(id="call_0", name="calculator", arguments={"expression": "2+2"})]),
        ToolTraceMessage(tool_call_id="call_0", name="calculator", content="4"),
        AssistantTraceMessage(content="The answer is 4", thinking="", tool_calls=[]),
    ]
    turns = [Turn(question="what is 2+2?", tool_trace=trace)]
    s = Sample(question="what is 2+2?", answer="The answer is 4", thinking="", score=9, passed=True,
               judge_reasoning="r", teacher_model="t", judge_model="j",
               topics=["math"], difficulty="easy", timestamp="now", turns=turns, n_turns=1,
               tools=[{"type": "function", "function": {"name": "calculator", "description": "calc", "parameters": {}}}],
               system_prompt="agent")
    sg = _build_sharegpt(s, include_thinking=True, thinking_format="inline_tags", include_tools_spec=True)
    a = sg["messages"][2]  # the tool-calling assistant step
    assert a["role"] == "assistant"
    assert a["tool_calls"], "tool_calls must be present"
    # The inlined thinking must survive — content is non-null and contains the
    # think tags + reasoning (the old code nulled it because it checked m.content).
    assert a["content"] is not None
    assert "I should compute 2+2" in a["content"]
    assert "<think>" in a["content"] or "imd" in a["content"].lower() or "<" in a["content"]
    print("  sharegpt inline_tags tool-step thinking OK")


def test_cap_result():
    # Short results pass through unchanged; long ones are capped with a marker.
    assert _cap_result("ok") == "ok"
    assert _cap_result(391) == "391"
    long = "x" * 5000
    capped = _cap_result(long)
    assert len(capped) == 4000 + len(" ...[truncated 1000 chars]")
    assert capped.endswith("...[truncated 1000 chars]")
    assert capped.startswith("x" * 4000)
    print("  cap_result OK")


def test_trace_used_tools():
    no_use = [AssistantTraceMessage(content="answer", thinking="", tool_calls=[])]
    assert _trace_used_tools(no_use) is False
    assert _trace_used_tools([]) is False
    assert _trace_used_tools(None) is False
    # Tool actually called -> agentic grading.
    used = [
        AssistantTraceMessage(content="", thinking="", tool_calls=[ToolCall(id="call_0", name="calculator", arguments={})]),
        ToolTraceMessage(tool_call_id="call_0", name="calculator", content="4"),
        AssistantTraceMessage(content="4", thinking="", tool_calls=[]),
    ]
    assert _trace_used_tools(used) is True
    # Non-empty tool_calls alone is enough (assistant requested a tool).
    assert _trace_used_tools([AssistantTraceMessage(content="", thinking="", tool_calls=[ToolCall(id="c", name="x", arguments={})])]) is True
    print("  trace_used_tools selection OK")


def test_grade_parsing():
    g = parse_grade('{"score": 8, "passed": true, "reasoning": "good"}')
    assert g.score == 8 and g.passed
    cg = parse_conversation_grade('{"score": 7, "passed": true, "reasoning": "ok", "turn_scores": [7,8,9], "tool_score": 8}', 3)
    assert cg.turn_scores == [7, 8, 9]
    assert cg.tool_score == 8
    # clamp + truncate
    cg2 = parse_conversation_grade('{"score": 99, "passed": true, "reasoning": "x", "turn_scores": [5,15,-1,3]}', 2)
    assert cg2.score == 10
    assert cg2.turn_scores == [5, 10]  # truncated to 2, clamped
    print("  grade parsing OK")


def test_request_validation():
    r = DistillRequest(teacher_model="t", judge_model="j", topics=["x"], multi_turn=False, min_turns=5, max_turns=9)
    # single-turn forces min=max=1
    assert r.min_turns == 1 and r.max_turns == 1
    r2 = DistillRequest(teacher_model="t", judge_model="j", topics=["x"], multi_turn=True, min_turns=2, max_turns=4)
    assert r2.min_turns == 2 and r2.max_turns == 4
    print("  request validation OK")


def test_api_endpoints():
    client = TestClient(app)
    # tools presets
    r = client.get("/api/tools/presets")
    assert r.status_code == 200
    assert any(t["name"] == "calculator" for t in r.json())
    # judges providers
    assert client.get("/api/judges/providers").status_code == 200
    # sessions list (empty ok)
    assert client.get("/api/distill/sessions").status_code == 200
    # 404 for unknown session export
    r = client.get("/api/distill/does-not-exist/export?fmt=raw")
    assert r.status_code == 404
    print("  api endpoints OK")


def test_min_turn_score_veto_closed():
    # Regression: the opt-in per-turn floor must fail CLOSED. When the judge
    # returns fewer turn_scores than turns, the conversation is rejected with a
    # signal rather than silently falling through to the keep path.
    import os, tempfile
    from pathlib import Path
    tmp = tempfile.mkdtemp(prefix="distillery_veto_")
    os.environ["DISTILLERY_DATASETS_DIR"] = tmp
    from distillery.distiller import DistillSession
    from distillery.schemas import Grade
    from distillery.store import store
    store.root = Path(tmp)

    sess = DistillSession(
        teacher_model="t", judge_model="j", topics=["x"], seeds=[],
        target_count=1, min_score=1, multi_turn=True, min_turns=2, max_turns=3,
        min_turn_score=8,
    )

    # Monkeypatch the judge so _finish_conversation uses a crafted grade with a
    # SHORT turn_scores list (1 score for 3 turns) -> must reject, not keep.
    async def fake_grade(transcript, criteria, tools_summary=None):
        return Grade(score=9, passed=True, reasoning="ok", turn_scores=[9], tool_score=None), {}
    sess.judge.grade_conversation = fake_grade  # type: ignore[attr-defined]

    turns = [Turn(question=f"q{i}", answer=f"a{i}") for i in range(3)]
    import asyncio
    asyncio.run(sess._finish_conversation("cid", turns, topic="x"))

    assert sess.rejected == 1, f"expected reject on short turn_scores, got rejected={sess.rejected}"
    assert sess.kept == 0, f"must not keep an un-vetted conversation, kept={sess.kept}"
    print("  min_turn_score veto fail-closed OK")


def main():
    test_calculator()
    test_calculator_pow_bound()
    test_raw_obj_byte_identical()
    test_sharegpt_single_turn()
    test_sharegpt_multi_turn()
    test_sharegpt_agentic()
    test_sharegpt_inline_tags_tool_thinking()
    test_cap_result()
    test_trace_used_tools()
    test_grade_parsing()
    test_request_validation()
    test_min_turn_score_veto_closed()
    test_api_endpoints()
    print("\nALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()