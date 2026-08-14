"""Live multi-turn smoke test against real Ollama (fully local, no API key).

Drives one multi-turn conversation through _process_conversation: turn 1 +
judge-generated follow-ups, then whole-conversation grading. Confirms turns
are produced, persisted, and that the plain multi-turn grade path runs.

Run: uv run python scripts/live_multiturn_smoke.py
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="distillery_mt_")
os.environ["DISTILLERY_DATASETS_DIR"] = _TMP

from distillery.distiller import DistillSession  # noqa: E402
from distillery.store import store  # noqa: E402

store.root = Path(_TMP)


async def main():
    sess = DistillSession(
        teacher_model="llama3.2:1b",
        judge_model="ollama/qwen2.5:1.5b-instruct",
        topics=["python"],
        seeds=["Explain decorators"],
        difficulty="easy",
        target_count=1,
        min_score=1,
        include_thinking=False,  # llama3.2:1b is non-thinking
        max_tokens=400,
        teacher_timeout=180.0,
        judge_timeout=120.0,
        multi_turn=True,
        min_turns=2,
        max_turns=3,
        history_include_thinking=False,
    )

    print("[1] running one multi-turn conversation...")
    await sess._process_conversation("Explain what a Python decorator is in simple terms.", topic="python")

    print(f"    kept={sess.kept} rejected={sess.rejected} grade_failed={sess.grade_failed} aborted={sess.aborted} errors={sess.error_count}")
    print(f"    last_grade: score={sess.last_grade.score} passed={sess.last_grade.passed} turn_scores={sess.last_grade.turn_scores}")
    print(f"    tokens: {sess.tokens}")

    assert sess.error_count == 0, f"unexpected errors: {sess.last_error}"
    # Either kept or rejected (a grade happened), not aborted/grade_failed.
    assert sess.kept + sess.rejected >= 1, "conversation did not produce a keep/reject decision"

    print("[2] reading back raw.jsonl...")
    raw_path = Path(_TMP) / sess.id / "raw.jsonl"
    rows = [json.loads(l) for l in raw_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert rows, "no raw sample written"
    r0 = rows[0]
    print(f"    raw keys: {sorted(r0.keys())}")
    turns = r0.get("turns", [])
    print(f"    n_turns stored: {len(turns)}")
    for i, t in enumerate(turns):
        print(f"      turn {i+1}: Q={t['question'][:60]!r} A={t['answer'][:60]!r}")

    # Plain multi-turn must NOT carry tools/system_prompt keys (byte-identical-ish).
    assert "tools" not in r0, "plain multi-turn sample should not carry tools"
    assert "system_prompt" not in r0, "plain multi-turn sample should not carry system_prompt"
    assert len(turns) >= 1, "expected at least one turn"

    print("\nLIVE MULTI-TURN SMOKE: PASS")


if __name__ == "__main__":
    asyncio.run(main())