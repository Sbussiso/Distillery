"""Live agent-trace smoke test against real Ollama.

Exercises the full agentic path: teacher (llama3.2:1b, tools-capable) is given a
calculator tool and an arithmetic question; we run _run_agent_turn, capture the
tool_trace, persist a Sample, and read back raw.jsonl + sharegpt to confirm the
OpenAI-style tool_calls + tool messages are recorded. No API key needed (fully
local: judge = ollama/qwen2.5:1.5b-instruct).

Run: uv run python scripts/live_agent_smoke.py
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

# Isolate datasets output before importing the package.
_TMP = tempfile.mkdtemp(prefix="distillery_smoke_")
os.environ["DISTILLERY_DATASETS_DIR"] = _TMP

from distillery.distiller import DistillSession  # noqa: E402
from distillery.schemas import Sample, ToolDef  # noqa: E402
from distillery.store import store  # noqa: E402

store.root = Path(_TMP)  # belt-and-suspenders: force the singleton to our temp dir


async def main():
    sess = DistillSession(
        teacher_model="llama3.2:1b",
        judge_model="ollama/qwen2.5:1.5b-instruct",
        topics=["arithmetic"],
        seeds=["What is 17 times 23?"],
        difficulty="easy",
        target_count=1,
        min_score=1,
        include_thinking=True,
        max_tokens=512,
        teacher_timeout=180.0,
        judge_timeout=120.0,
        multi_turn=False,
        tools=[ToolDef(
            name="calculator",
            description="Evaluate an arithmetic expression. Supports + - * / ** and constants pi, e, tau.",
            parameters={
                "type": "object",
                "properties": {"expression": {"type": "string", "description": "The arithmetic expression to evaluate."}},
                "required": ["expression"],
            },
            exec_policy="builtin",
        )],
        max_tool_rounds=4,
        tool_call_timeout=30.0,
    )

    print(f"[1] probing tools capability on {sess.teacher_model}...")
    supported = await sess.ollama.probe_tools(sess.teacher_model)
    print(f"    tools supported: {supported}")
    assert supported, "llama3.2:1b should support tools"

    print("[2] running agent turn (teacher + calculator tool)...")
    turn = await sess._run_agent_turn(
        "Use the calculator tool to compute 17 * 23, then tell me the answer.",
        prior_turns=[],
        conv_id="smoke",
        turn_idx=1,
    )
    print(f"    answer: {turn.answer!r}")
    print(f"    thinking chars: {len(turn.thinking)}")
    print(f"    tool_trace steps: {len(turn.tool_trace)}")
    for i, m in enumerate(turn.tool_trace):
        if hasattr(m, "tool_calls"):
            calls = [c.name for c in m.tool_calls]
            print(f"      [{i}] assistant tool_calls={calls} content={m.content!r}")
        else:
            print(f"      [{i}] tool {m.name} result={m.content!r}")

    used_tool = any(hasattr(m, "tool_calls") and m.tool_calls for m in turn.tool_trace)
    print(f"    used a tool: {used_tool}")

    # Persist + read back.
    print("[3] persisting sample + reading back raw.jsonl / sharegpt...")
    sample = Sample(
        question="Use the calculator tool to compute 17 * 23, then tell me the answer.",
        answer=turn.answer, thinking=turn.thinking, score=9, passed=True,
        judge_reasoning="smoke", teacher_model=sess.teacher_model, judge_model=sess.judge_model,
        topics=sess.topics, difficulty="easy", timestamp="2026-08-11T00:00:00Z",
        turns=[turn], conversation_id="smoke",
        tools=sess._sample_tool_specs, system_prompt=sess.teacher_system_prompt,
        turn_scores=[9], tool_score=9 if used_tool else None,
    )
    store.append_sample(sess.id, sample)

    raw_path = Path(_TMP) / sess.id / "raw.jsonl"
    rows = [json.loads(l) for l in raw_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"    raw rows: {len(rows)}")
    r0 = rows[0]
    print(f"    raw keys: {sorted(r0.keys())}")
    print(f"    raw has turns: {'turns' in r0 and len(r0['turns'])>0}")
    print(f"    raw has tools: {'tools' in r0}")
    if r0.get("turns"):
        t0 = r0["turns"][0]
        print(f"    turn0 tool_trace len: {len(t0.get('tool_trace', []))}")

    # Export sharegpt and confirm OpenAI tool-call format.
    p = store.export_path(sess.id, "sharegpt", include_thinking=True, thinking_format="separate_field", include_tools_spec=True)
    sg = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    msgs = sg[0]["messages"]
    print(f"[4] sharegpt messages: {len(msgs)}")
    for m in msgs:
        role = m["role"]
        if "tool_calls" in m:
            tc = m["tool_calls"][0]
            print(f"    {role}: tool_call {tc['function']['name']} args={tc['function']['arguments']!r} (type={type(tc['function']['arguments']).__name__})")
        elif role == "tool":
            print(f"    {role}: name={m.get('name')} tool_call_id={m.get('tool_call_id')} content={m.get('content')!r}")
        else:
            c = m.get("content")
            print(f"    {role}: {str(c)[:60]!r}{' +thinking' if m.get('thinking') else ''}")

    # Assertions on the exported format.
    sys_msg = next((m for m in msgs if m["role"] == "system"), None)
    assert sys_msg and "tools" in sys_msg, "system message should carry tools"
    tool_call_msgs = [m for m in msgs if m.get("tool_calls")]
    tool_result_msgs = [m for m in msgs if m["role"] == "tool"]
    if used_tool:
        assert tool_call_msgs, "expected at least one assistant tool_calls message"
        tc = tool_call_msgs[0]["tool_calls"][0]
        assert tc["type"] == "function"
        assert isinstance(tc["function"]["arguments"], str), "arguments must be a JSON string in export"
        json.loads(tc["function"]["arguments"])  # parses
        assert tool_result_msgs, "expected tool result messages"
        assert tool_result_msgs[0]["tool_call_id"] == tc["id"]
        assert tool_result_msgs[0]["name"] == tc["function"]["name"]
    print("\nLIVE AGENT-TRACE SMOKE: PASS")


if __name__ == "__main__":
    asyncio.run(main())