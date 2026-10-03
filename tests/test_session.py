"""Session lifecycle tests with a stubbed judge and teacher (no network)."""
from __future__ import annotations

import asyncio

import pytest

from distillery import distiller as D
from distillery.judge import JudgeError
from distillery.schemas import Grade, Turn
from distillery.sessions import SessionRegistry
from distillery.store import store


def make_session(**kw) -> D.DistillSession:
    args = dict(teacher_model="t", judge_model="j", topics=["a"], seeds=[], target_count=3)
    args.update(kw)
    return D.DistillSession(**args)


def stub_round(s: D.DistillSession, *, delay: float = 0.0, score: int = 9) -> None:
    """Questions q1, q2, ...; teacher answers after `delay`; judge grades `score`."""
    n = 0

    async def gen(*a, **k):
        nonlocal n
        n += 1
        return f"question {n}"

    async def chat(*a, **k):
        await asyncio.sleep(delay)
        return {"content": "answer", "thinking": ""}

    async def grade(*a, **k):
        return Grade(score=score, passed=score >= 7, reasoning="ok"), {}

    s.judge.generate_question = gen
    s.ollama.chat = chat
    s.judge.grade = grade


def test_producer_fails_session_after_repeated_judge_errors(monkeypatch):
    monkeypatch.setattr(D, "_QGEN_BACKOFF_CAP", 0.01)
    s = make_session()
    calls = 0

    async def bad(*a, **k):
        nonlocal calls
        calls += 1
        raise JudgeError("401 bad key")

    s.judge.generate_question = bad
    asyncio.run(asyncio.wait_for(s.run(), timeout=10))
    assert s.status == "errored"
    assert calls == D._QGEN_MAX_FAILURES
    assert "401 bad key" in (s.last_error or "")


def test_completes_at_target():
    s = make_session(target_count=3)
    stub_round(s)
    asyncio.run(asyncio.wait_for(s.run(), timeout=10))
    assert s.status == "completed"
    assert s.kept == 3
    assert store.count_samples(s.id) == 3


def test_delete_cancels_workers_and_keeps_directory_gone():
    async def scenario():
        reg = SessionRegistry()
        s = make_session(target_count=100, concurrency=2)
        stub_round(s, delay=0.2)
        reg.start(s)
        await asyncio.sleep(0.6)
        d = store.root / s.id
        assert d.exists()
        assert await reg.delete(s.id) is True
        await asyncio.sleep(0.5)
        others = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        return d, others

    d, others = asyncio.run(scenario())
    assert others == []
    assert not d.exists()


def test_stop_does_not_start_queued_rounds():
    async def scenario():
        s = make_session(target_count=100, concurrency=1)
        stub_round(s, delay=0.2)
        task = asyncio.create_task(s.run())
        await asyncio.sleep(0.5)  # queue fills while the worker is busy
        assert s._queue is not None and s._queue.qsize() > 0
        graded_before = s.kept + s.rejected
        s.stop()
        await asyncio.wait_for(task, timeout=2)
        return s, graded_before

    s, graded_before = asyncio.run(scenario())
    assert s.status == "stopped"
    assert s.kept + s.rejected <= graded_before + 1  # only the in-flight round


def test_parse_failed_grade_counts_as_grade_failed_with_turn_floor():
    s = make_session(multi_turn=True, min_turns=1, max_turns=2, min_turn_score=5)

    async def unparsed(*a, **k):
        return Grade(score=0, passed=False, reasoning="parse_failed"), {}

    s.judge.grade_conversation = unparsed
    turns = [Turn(question="q", answer="a")]
    asyncio.run(s._finish_conversation("c1", turns, topic="a"))
    assert s.grade_failed == 1
    assert s.rejected == 0


def test_all_judge_calls_count_tokens(monkeypatch):
    s = make_session()

    class Usage:
        prompt_tokens, completion_tokens, total_tokens = 10, 5, 15

    class Resp:
        usage = Usage()
        choices = [type("C", (), {"message": type("M", (), {"content": "What is 2+2?"})()})()]

    async def fake_completion(**kw):
        return Resp()

    monkeypatch.setattr("distillery.judge.litellm.acompletion", fake_completion)
    asyncio.run(s.judge.generate_question(["a"], [], "any", [], {}))
    assert s.tokens == {"prompt": 10, "completion": 5, "total": 15}


def test_every_subscriber_gets_every_event_and_inflight_replay():
    from distillery.schemas import ProgressEvent

    async def scenario():
        s = make_session()
        a = s.subscribe()
        await s._emit(ProgressEvent(type="conversation_started", conversation_id="c1"))
        await s._emit(ProgressEvent(type="turn_answer", conversation_id="c1", turn=1))
        late = s.subscribe()  # joins mid-conversation
        await s._emit(ProgressEvent(type="conversation_graded", conversation_id="c1"))
        after = s.subscribe()  # joins after it finished
        drain = lambda q: [q.get_nowait().type for _ in range(q.qsize())]
        return drain(a), drain(late), drain(after)

    a, late, after = asyncio.run(scenario())
    assert a == ["conversation_started", "turn_answer", "conversation_graded"]
    assert late == ["conversation_started", "turn_answer", "conversation_graded"]
    assert after == []


def test_resume_keeps_judge_settings():
    s = make_session(judge_reasoning_effort="high", judge_api_key="sk-test")
    asyncio.run(s._persist())

    async def scenario():
        reg = SessionRegistry()
        reg.create(s)
        s.status = "stopped"
        resumed = reg.resume(s.id)
        resumed.stop()
        await reg.delete(s.id)
        return resumed

    resumed = asyncio.run(scenario())
    assert resumed.judge.reasoning_effort == "high"
    assert resumed.judge.api_key == "sk-test"


def test_session_fails_after_repeated_round_errors():
    s = make_session(target_count=100)
    stub_round(s)

    async def down(*a, **k):
        raise RuntimeError("connection refused")

    s.ollama.chat = down
    asyncio.run(asyncio.wait_for(s.run(), timeout=10))
    assert s.status == "errored"
    assert "connection refused" in (s.last_error or "")
    assert s.error_count < 20  # stopped promptly instead of spinning


def test_conversation_rounds_report_success():
    s = make_session(multi_turn=True, min_turns=1, max_turns=1, target_count=2)
    stub_round(s)

    async def grade_conv(*a, **k):
        return Grade(score=9, passed=True, reasoning="ok", turn_scores=[9]), {}

    s.judge.grade_conversation = grade_conv
    asyncio.run(asyncio.wait_for(s.run(), timeout=10))
    assert s.status == "completed"
    assert s.kept == 2


def test_interrupted_session_is_reported_as_stopped():
    from fastapi.testclient import TestClient

    from distillery.app import app

    s = make_session()
    asyncio.run(s._persist())  # a crash leaves status "running" on disk
    assert [m.status for m in SessionRegistry().list_metas()] == ["stopped"]
    assert TestClient(app).get(f"/api/distill/{s.id}").json()["status"] == "stopped"
