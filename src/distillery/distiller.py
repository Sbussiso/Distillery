"""The distillation orchestrator.

A DistillSession runs one producer coroutine (the only question generator, so
dedup holds) feeding an asyncio.Queue, plus N worker coroutines that each pop
an opening question and drive a conversation to completion.

Three modes share one code path:
  - single-turn (legacy): one Q -> one A -> grade()
  - multi-turn: Q1 -> A1 -> followup -> A2 -> ... -> grade_conversation()
  - agentic (tools): each turn is an inner agent loop (teacher calls tools, we
    resolve/simulate them, feed results back) until a final answer or
    max_tool_rounds; the full tool_trace is recorded so a student can be trained
    to reproduce agentic behavior.

State is guarded by a lock; progress is emitted to a queue consumed by the
WebSocket endpoint; session.json is rewritten each round so a crash or stop is
resumable.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

from .judge import Judge, JudgeError
from .ollama import OllamaClient, OllamaError, to_ollama_tools
from .prompts import FINAL_ANSWER_NO_TOOLS
from .schemas import (
    AssistantTraceMessage,
    Grade,
    ProgressEvent,
    Sample,
    SessionStatus,
    ToolCall,
    ToolDef,
    ToolSpec,
    TokenTotals,
    ToolTraceMessage,
    Turn,
)
from .store import store
from .tools_builtin import BUILTIN_EXECUTORS

_DEFAULT_TEACHER_SYSTEM = (
    "You are a helpful, accurate assistant. If the problem warrants it, reason "
    "step by step before giving your final answer."
)

# Child-process runner for builtin tool executors. Runs in a fresh `python -c`
# process that imports ONLY tools_builtin (no litellm/fastapi), calls the
# registered executor, and writes the result to stdout. A non-zero exit marks
# a runner-level error (the calculator's own "[error: ...]" results exit 0 and
# are legitimate). This lets us hard-kill a runaway builtin on timeout —
# asyncio.to_thread cannot cancel a blocked executor thread.
_BUILTIN_RUNNER_SCRIPT = r"""
import json, sys
from distillery.tools_builtin import BUILTIN_EXECUTORS
try:
    data = json.loads(sys.argv[1])
    fn = BUILTIN_EXECUTORS.get(data["name"])
    if fn is None:
        sys.stdout.write("[error: builtin not registered]")
        sys.stdout.flush()
        sys.exit(1)
    sys.stdout.write(fn(data["args"]))
    sys.stdout.flush()
except Exception as e:
    sys.stdout.write("[error: " + str(e) + "]")
    sys.stdout.flush()
    sys.exit(1)
"""

# Cap on tool-result strings fed back into the teacher history and persisted in
# the tool_trace. The agentic-judge transcript has its own (smaller) cap; this
# protects the teacher-feedback path + on-disk payload from 100KB+ blowups.
_RESULT_CAP = 4000

# Producer backoff when no new question can be obtained (judge error, or only
# duplicates): wait 1s, 2s, 4s, ... (capped) between attempts, and fail the
# session after this many consecutive misses instead of spinning forever
# against a broken or rate-limited judge.
_QGEN_MAX_FAILURES = 5
_QGEN_BACKOFF_CAP = 30.0

# Fail the session after this many rounds in a row end in an error (e.g.
# Ollama down, judge rejecting every grade call). Without it, workers fail
# instantly in a hot loop while the producer keeps paying for new questions.
_MAX_FAILED_ROUNDS = 5


class AgentLoopAborted(RuntimeError):
    """Raised by the deterministic abort gate (empty answer or repeated
    follow-up below min_turns). Maps to rejected+aborted (or partial-keep)."""


def _cap_result(s: Any, limit: int = _RESULT_CAP) -> str:
    """Stringify and cap a tool result so it can't bloat the teacher context or
    the persisted trace. The grading transcript applies its own smaller cap."""
    s = str(s)
    return s if len(s) <= limit else s[:limit] + f" ...[truncated {len(s) - limit} chars]"


def _put_drop_oldest(q: asyncio.Queue, item: Any) -> None:
    """Non-blocking put; if a client isn't draining, drop its oldest event
    rather than grow memory without bound."""
    try:
        q.put_nowait(item)
    except asyncio.QueueFull:
        try:
            q.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            q.put_nowait(item)
        except asyncio.QueueFull:
            pass


def _normalize(q: str) -> str:
    """Lexical normalizer for question dedup (lowercase, alnum only)."""
    return re.sub(r"[^a-z0-9]", "", q.lower())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DistillSession:
    def __init__(
        self,
        *,
        teacher_model: str,
        judge_model: str,
        topics: list[str],
        seeds: list[str],
        difficulty: str = "any",
        target_count: int = 10,
        min_score: int = 7,
        include_thinking: bool = True,
        teacher_system_prompt: str | None = None,
        grading_criteria: str | None = None,
        concurrency: int = 1,
        max_tokens: int = 2048,
        teacher_timeout: float = 180.0,
        judge_timeout: float = 120.0,
        judge_api_key: str | None = None,
        judge_reasoning_effort: str | None = None,
        # multi-turn
        multi_turn: bool = False,
        min_turns: int = 1,
        max_turns: int = 1,
        history_include_thinking: bool = True,
        min_turn_score: int | None = None,
        # tools
        tools: list[ToolDef] | None = None,
        max_tool_rounds: int = 6,
        tool_call_timeout: float = 60.0,
        keep_partial_on_abort: bool = False,
        session_id: str | None = None,
    ) -> None:
        self.id = session_id or uuid.uuid4().hex[:12]

        # config
        self.teacher_model = teacher_model
        self.judge_model = judge_model
        self.topics = list(topics)
        self.seeds = list(seeds)
        self.difficulty = difficulty
        self.target_count = target_count
        self.min_score = min_score
        self.include_thinking = include_thinking
        self.teacher_system_prompt = teacher_system_prompt or _DEFAULT_TEACHER_SYSTEM
        self.grading_criteria = grading_criteria
        self.concurrency = max(1, concurrency)
        self.max_tokens = max_tokens
        self.teacher_timeout = teacher_timeout
        self.judge_timeout = judge_timeout

        # multi-turn config
        self.multi_turn = multi_turn
        self.min_turns = min_turns
        self.max_turns = max_turns
        self.history_include_thinking = history_include_thinking
        self.min_turn_score = min_turn_score

        # tools config
        self.tools: list[ToolDef] = list(tools or [])
        self.max_tool_rounds = max_tool_rounds
        self.tool_call_timeout = tool_call_timeout
        self.keep_partial_on_abort = keep_partial_on_abort
        self._tool_by_name: dict[str, ToolDef] = {td.name: td for td in self.tools}
        self._ollama_tools: list[dict[str, Any]] = to_ollama_tools(self.tools)
        self._sample_tool_specs: list[ToolSpec] = [
            ToolSpec(type="function", function={
                "name": td.name, "description": td.description, "parameters": td.parameters,
            })
            for td in self.tools if td.exec_policy != "off"
        ]
        self._tools_active = bool(self._ollama_tools)
        self._call_counter = 0

        # state (guarded)
        self.status: str = "running"
        self.kept = 0
        self.rejected = 0
        self.grade_failed = 0
        self.error_count = 0
        self.aborted = 0
        self._failed_rounds = 0  # consecutive rounds that ended in an error
        self.topic_counts: dict[str, int] = {t: 0 for t in self.topics}
        self.asked: list[str] = []
        self._asked_set: set[str] = set()
        self.tokens = {"prompt": 0, "completion": 0, "total": 0}

        # last-round view
        self.last_question: str | None = None
        self.last_answer: str | None = None
        self.last_thinking: str | None = None
        self.last_grade: Grade | None = None
        self.last_error: str | None = None

        # bookkeeping
        self.created_at = _now_iso()
        self.updated_at = self.created_at

        # clients + sync primitives (created at run time)
        self.judge = Judge(
            judge_model,
            api_key=judge_api_key,
            reasoning_effort=judge_reasoning_effort,
            max_tokens=max_tokens,
            timeout=judge_timeout,
        )
        self.judge.on_usage = self._add_usage
        self.ollama = OllamaClient(timeout=teacher_timeout)
        self._stop = asyncio.Event()
        self._lock = asyncio.Lock()
        self._queue: asyncio.Queue[tuple[str, str | None]] | None = None
        # One bounded queue per connected WebSocket client, so every client
        # sees every event (a single shared queue split events between tabs).
        # Nothing is buffered while no client is connected: finished rounds
        # are read back from disk, and the events of conversations still in
        # flight are kept in _live_events and replayed to a new subscriber, so
        # a client never sees a finished conversation twice or a half one.
        self._subscribers: set[asyncio.Queue[ProgressEvent]] = set()
        self._live_events: dict[str, list[ProgressEvent]] = {}
        # True when this session was rebuilt from disk by from_disk(). Guards
        # run() from re-probing tool capability on resume (the capability was
        # already determined in the original run and persisted in session.json;
        # a transient Ollama hiccup during resume must not silently downgrade
        # an agentic session to the non-agentic path).
        self._resumed = False

    # ---- public API ---------------------------------------------------------
    async def run(self) -> None:
        """Run the producer + workers until target reached or stopped."""
        self._queue = asyncio.Queue(maxsize=self.concurrency * 4)
        self.status = "running"

        # Probe tool capability once so we can skip tools (and avoid a wasted
        # 400->retry per call) when the teacher model lacks the tools API.
        # Skip on resume: _tools_active was already determined in the original
        # run and restored by from_disk; re-probing under a transient Ollama
        # hiccup would silently downgrade an agentic session.
        if self._tools_active and not self._resumed:
            try:
                supported = await self.ollama.probe_tools(self.teacher_model)
            except Exception:
                supported = False
            if not supported:
                self._tools_active = False
                await self._emit(ProgressEvent(
                    type="tool_unsupported",
                    message=f"teacher model '{self.teacher_model}' does not support tools; continuing without tools",
                ))

        await self._persist()

        producer = asyncio.create_task(self._producer())
        workers = [asyncio.create_task(self._worker(i)) for i in range(self.concurrency)]

        try:
            try:
                await producer
            except Exception as e:  # noqa: BLE001
                await self._fail(e)
            await asyncio.gather(*workers, return_exceptions=True)
        except asyncio.CancelledError:
            # Cancelled from outside (registry.delete). The producer/workers
            # are separate tasks, so cancel and await them too; otherwise an
            # in-flight round could write into a directory being deleted.
            for t in (producer, *workers):
                t.cancel()
            await asyncio.gather(producer, *workers, return_exceptions=True)
            self.status = "stopped"
            raise

        if self.status == "running":
            self.status = "completed" if self.kept >= self.target_count else "stopped"
        await self._persist()
        await self._emit(ProgressEvent(type="complete" if self.status == "completed" else "stopped", status=self.status_obj()))

    def stop(self) -> None:
        self._stop.set()

    def status_obj(self) -> SessionStatus:
        return SessionStatus(
            id=self.id,
            teacher_model=self.teacher_model,
            judge_model=self.judge_model,
            topics=self.topics,
            status=self.status,  # type: ignore[arg-type]
            target_count=self.target_count,
            kept=self.kept,
            rejected=self.rejected,
            grade_failed=self.grade_failed,
            error_count=self.error_count,
            topic_counts=self.topic_counts,
            tokens=TokenTotals(**self.tokens),
            multi_turn=self.multi_turn,
            min_turns=self.min_turns,
            max_turns=self.max_turns,
            aborted=self.aborted,
            tools_active=self._tools_active,
            last_question=self.last_question,
            last_answer=self.last_answer,
            last_thinking=self.last_thinking,
            last_grade=self.last_grade,
            last_error=self.last_error,
        )

    # ---- producer -----------------------------------------------------------
    async def _producer(self) -> None:
        assert self._queue is not None
        try:
            await self._produce()
        finally:
            self._stop.set()  # let workers drain and exit (also on failure)

    async def _produce(self) -> None:
        assert self._queue is not None
        misses = 0
        while not self._stop.is_set():
            async with self._lock:
                if self.kept >= self.target_count:
                    break
                asked_snapshot = list(self.asked)
                topic_counts_snapshot = dict(self.topic_counts)
                steer = self._steer_topic()

            question: str | None = None
            last_err = "only empty or duplicate questions generated"
            for _ in range(5):  # try a few times to get a non-duplicate
                try:
                    q = await self.judge.generate_question(
                        self.topics, self.seeds, self.difficulty, asked_snapshot, topic_counts_snapshot
                    )
                except JudgeError as e:
                    last_err = f"question gen failed: {e}"
                    await self._record_error(last_err)
                    break
                if not q:
                    continue
                norm = _normalize(q)
                async with self._lock:
                    if norm in self._asked_set:
                        continue  # dup, try again
                    self._asked_set.add(norm)
                    self.asked.append(q)
                    question = q
                    self.last_question = q
                break

            if not question:
                misses += 1
                if misses >= _QGEN_MAX_FAILURES:
                    raise RuntimeError(f"no new question after {misses} attempts: {last_err}")
                delay = min(2.0 ** (misses - 1), _QGEN_BACKOFF_CAP)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
                continue
            misses = 0
            await self._emit(ProgressEvent(type="question", question=question, topic=steer, tools_active=self._tools_active))
            # Bounded put: when the target is reached, workers break out of
            # their loop WITHOUT draining the queue, so a plain put on a full
            # queue (maxsize = concurrency*4) would block forever — freezing the
            # session at "running" and never emitting complete/stopped. Re-check
            # the stop flag while waiting for a slot so the producer can exit.
            while not self._stop.is_set():
                try:
                    await asyncio.wait_for(self._queue.put((question, steer)), timeout=0.5)
                    break
                except asyncio.TimeoutError:
                    continue
            # If stop was set, the item is dropped — fine, workers are exiting.

    def _steer_topic(self) -> str | None:
        if not self.topics:
            return None
        return min(self.topics, key=lambda t: self.topic_counts.get(t, 0))

    # ---- worker -------------------------------------------------------------
    async def _worker(self, _idx: int) -> None:
        assert self._queue is not None
        while True:
            # Exit as soon as stop is set (user Stop, target reached, or the
            # producer failed). Rounds already in progress still finish, but
            # queued questions are not started; they stay in the asked-set.
            if self._stop.is_set():
                break
            try:
                question, topic = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue

            try:
                ok = await self._process_round(question, topic)
            except Exception as e:  # noqa: BLE001 - never let a worker die
                await self._record_error(f"round failed: {e}")
                ok = False

            if ok:
                self._failed_rounds = 0
            else:
                self._failed_rounds += 1
                if self._failed_rounds >= _MAX_FAILED_ROUNDS and self.status == "running":
                    await self._fail(RuntimeError(
                        f"{self._failed_rounds} rounds in a row failed; last error: {self.last_error}"
                    ))
                    self._stop.set()
                    break

            async with self._lock:
                if self.kept >= self.target_count:
                    self._stop.set()
                    break

    # ---- round dispatch -----------------------------------------------------
    async def _process_round(self, question: str, topic: str | None) -> bool:
        """Run one round. Returns False if it ended in an error (single-turn
        errors raise instead)."""
        if self.multi_turn or self._tools_active:
            return await self._process_conversation(question, topic)
        await self._process_single(question, topic)
        return True

    # ---- single-turn (legacy, byte-identical path) -------------------------
    async def _process_single(self, question: str, topic: str | None) -> None:
        messages: list[dict[str, str]] = []
        if self.teacher_system_prompt:
            messages.append({"role": "system", "content": self.teacher_system_prompt})
        messages.append({"role": "user", "content": question})

        res = await self.ollama.chat(
            self.teacher_model,
            messages,
            think=self.include_thinking,
            max_tokens=self.max_tokens,
            timeout=self.teacher_timeout,
        )
        answer = res["content"]
        thinking = res["thinking"] if self.include_thinking else ""

        async with self._lock:
            self.last_answer = answer
            self.last_thinking = thinking
        await self._emit(
            ProgressEvent(type="answer", question=question, answer=answer, thinking=thinking or None)
        )

        grade, _ = await self.judge.grade(question, answer, self.grading_criteria)
        async with self._lock:
            self.last_grade = grade
        await self._emit(ProgressEvent(type="grade", question=question, grade=grade))

        if grade.reasoning == "parse_failed" and grade.score == 0:
            async with self._lock:
                self.grade_failed += 1
            await self._emit(ProgressEvent(type="grade_failed", question=question, grade=grade, grade_failed=self.grade_failed))
        elif grade.score >= self.min_score:
            sample = Sample(
                question=question,
                answer=answer,
                thinking=thinking,
                score=grade.score,
                passed=True,
                judge_reasoning=grade.reasoning,
                teacher_model=self.teacher_model,
                judge_model=self.judge_model,
                topics=self.topics,
                difficulty=self.difficulty,
                timestamp=_now_iso(),
            )
            store.append_sample(self.id, sample)
            async with self._lock:
                self.kept += 1
                if topic:
                    self.topic_counts[topic] = self.topic_counts.get(topic, 0) + 1
            await self._emit(
                ProgressEvent(type="kept", question=question, grade=grade, kept=self.kept, target=self.target_count, topic=topic)
            )
        else:
            async with self._lock:
                self.rejected += 1
            await self._emit(ProgressEvent(type="rejected", question=question, grade=grade, rejected=self.rejected))

        await self._persist()

    # ---- multi-turn / agentic conversation ---------------------------------
    async def _process_conversation(self, question: str, topic: str | None) -> bool:
        conv_id = uuid.uuid4().hex[:8]
        turns: list[Turn] = []
        await self._emit(ProgressEvent(
            type="conversation_started", conversation_id=conv_id, question=question,
            topic=topic, tools_active=self._tools_active, turn=1, turn_count=1,
            target=self.target_count,
        ))
        try:
            # Turn 1.
            turn = await self._answer_turn(question, turns, conv_id, 1)
            if not turn.answer.strip():
                raise AgentLoopAborted("empty answer on turn 1")
            turns.append(turn)

            # Follow-up loop.
            while len(turns) < self.max_turns:
                can_done = len(turns) >= self.min_turns
                followup = await self.judge.generate_followup(
                    self.topics, turns, len(turns), self.min_turns, self.max_turns, can_done
                )
                if followup is None:
                    if can_done:
                        break  # judge signalled [[DONE]] and min_turns met
                    # Below min_turns and the judge returned empty/[[DONE]] despite
                    # being told not to. This is a worse failure than a repeat, so
                    # mirror the repeat-gate: retry once, strictly; still empty ->
                    # deterministic abort (do NOT silently grade a short conv).
                    followup = await self.judge.generate_followup(
                        self.topics, turns, len(turns), self.min_turns, self.max_turns,
                        can_done, extra_strict=True,
                    )
                    if not followup:
                        raise AgentLoopAborted("judge returned empty/DONE below min_turns")
                if self._conv_repeat(turns, followup):
                    if can_done:
                        break  # natural end
                    # Below min_turns and the judge repeated itself: ask once
                    # more, strictly. Still repeated -> deterministic abort.
                    followup = await self.judge.generate_followup(
                        self.topics, turns, len(turns), self.min_turns, self.max_turns,
                        can_done, extra_strict=True,
                    )
                    if not followup or self._conv_repeat(turns, followup):
                        raise AgentLoopAborted("repeated follow-up below min_turns")
                await self._emit(ProgressEvent(
                    type="turn_followup", conversation_id=conv_id, question=followup,
                    turn=len(turns) + 1, turn_count=len(turns) + 1,
                ))
                turn = await self._answer_turn(followup, turns, conv_id, len(turns) + 1)
                if not turn.answer.strip():
                    raise AgentLoopAborted("empty answer")
                turns.append(turn)

            # Completed normally -> grade the whole conversation.
            await self._finish_conversation(conv_id, turns, topic)
        except AgentLoopAborted as e:
            await self._abort_conversation(conv_id, turns, topic, reason=str(e))
        except OllamaError as e:
            await self._record_error(f"conversation failed (ollama): {e}")
            return False
        except JudgeError as e:
            await self._record_error(f"conversation failed (judge): {e}")
            return False
        finally:
            # Drop replay state if it ended without conversation_graded.
            self._live_events.pop(conv_id, None)
            await self._persist()
        return True

    async def _answer_turn(self, question: str, prior_turns: list[Turn], conv_id: str, turn_idx: int) -> Turn:
        if self._tools_active:
            turn = await self._run_agent_turn(question, prior_turns, conv_id, turn_idx)
        else:
            messages = self._teacher_history(prior_turns)
            messages.append({"role": "user", "content": question})
            res = await self.ollama.chat(
                self.teacher_model, messages,
                think=self.include_thinking, max_tokens=self.max_tokens,
                timeout=self.teacher_timeout,
            )
            turn = Turn(
                question=question,
                answer=res["content"],
                thinking=res["thinking"] if self.include_thinking else "",
            )
        async with self._lock:
            self.last_answer = turn.answer
            self.last_thinking = turn.thinking
        await self._emit(ProgressEvent(
            type="turn_answer", conversation_id=conv_id, turn=turn_idx, turn_count=turn_idx,
            question=question, answer=turn.answer, thinking=turn.thinking or None,
        ))
        return turn

    async def _finish_conversation(self, conv_id: str, turns: list[Turn], topic: str | None) -> None:
        grade, _ = await self.judge.grade_conversation(
            turns, self.grading_criteria, tools_summary=self._tools_summary()
        )
        async with self._lock:
            self.last_grade = grade
        await self._emit(ProgressEvent(type="grade", grade=grade, conversation_id=conv_id, turn_count=len(turns)))

        # A grade the judge failed to parse is a grade failure, not a rejection,
        # whether or not a per-turn floor is configured.
        if grade.reasoning == "parse_failed" and grade.score == 0:
            async with self._lock:
                self.grade_failed += 1
            await self._emit(ProgressEvent(type="grade_failed", grade=grade, conversation_id=conv_id, grade_failed=self.grade_failed))
            await self._emit(ProgressEvent(
                type="conversation_graded", conversation_id=conv_id, grade=grade,
                grade_failed=self.grade_failed, turn_count=len(turns),
            ))
            return

        # Opt-in per-turn veto. Fail CLOSED: if the judge didn't return exactly
        # one turn_score per turn, the floor can't be verified for every turn, so
        # reject with an audible signal rather than silently keeping an
        # un-vetted conversation that the user explicitly opted into a floor for.
        if self.min_turn_score is not None:
            if len(grade.turn_scores) != len(turns):
                async with self._lock:
                    self.rejected += 1
                await self._emit(ProgressEvent(
                    type="conversation_graded", conversation_id=conv_id, grade=grade,
                    rejected=self.rejected, turn_count=len(turns),
                    message=f"min_turn_score veto skipped: got {len(grade.turn_scores)} "
                    f"turn_scores for {len(turns)} turns",
                ))
                return
            if any(ts < self.min_turn_score for ts in grade.turn_scores):
                async with self._lock:
                    self.rejected += 1
                await self._emit(ProgressEvent(
                    type="conversation_graded", conversation_id=conv_id, grade=grade,
                    rejected=self.rejected, turn_count=len(turns), message="min_turn_score veto",
                ))
                return

        if grade.score >= self.min_score:
            sample = self._build_sample(turns, conv_id, grade)
            store.append_sample(self.id, sample)
            async with self._lock:
                self.kept += 1
                if topic:
                    self.topic_counts[topic] = self.topic_counts.get(topic, 0) + 1
            await self._emit(ProgressEvent(
                type="conversation_graded", conversation_id=conv_id, grade=grade,
                kept=self.kept, target=self.target_count, topic=topic, turn_count=len(turns),
            ))
        else:
            async with self._lock:
                self.rejected += 1
            await self._emit(ProgressEvent(
                type="conversation_graded", conversation_id=conv_id, grade=grade,
                rejected=self.rejected, turn_count=len(turns),
            ))

    async def _abort_conversation(self, conv_id: str, turns: list[Turn], topic: str | None, *, reason: str) -> None:
        async with self._lock:
            self.aborted += 1
        await self._emit(ProgressEvent(
            type="conversation_aborted", conversation_id=conv_id, aborted=self.aborted,
            turn_count=len(turns), message=reason,
        ))
        if self.keep_partial_on_abort and turns:
            # Grade the completed turns as a partial conversation.
            await self._finish_conversation(conv_id, turns, topic)
        else:
            async with self._lock:
                self.rejected += 1
            await self._emit(ProgressEvent(
                type="conversation_graded", conversation_id=conv_id, rejected=self.rejected,
                turn_count=len(turns), message=f"aborted: {reason}",
            ))

    def _conv_repeat(self, turns: list[Turn], question: str) -> bool:
        nq = _normalize(question)
        return any(_normalize(t.question) == nq for t in turns)

    def _build_sample(self, turns: list[Turn], conv_id: str, grade: Grade) -> Sample:
        t0 = turns[0]
        tools = self._sample_tool_specs if self._tools_active else None
        system_prompt = self.teacher_system_prompt if self._tools_active else None
        return Sample(
            question=t0.question,
            answer=t0.answer,
            thinking=t0.thinking,
            score=grade.score,
            passed=True,
            judge_reasoning=grade.reasoning,
            teacher_model=self.teacher_model,
            judge_model=self.judge_model,
            topics=self.topics,
            difficulty=self.difficulty,
            timestamp=_now_iso(),
            turns=turns,
            conversation_id=conv_id,
            tools=tools,
            system_prompt=system_prompt,
            turn_scores=grade.turn_scores or None,
            tool_score=grade.tool_score,
        )

    def _tools_summary(self) -> str | None:
        if not self._tools_active or not self.tools:
            return None
        parts = [f"{td.name} ({td.exec_policy})" for td in self.tools if td.exec_policy != "off"]
        return ", ".join(parts) if parts else None

    # ---- inner agent loop (per turn, when tools active) --------------------
    async def _run_agent_turn(self, question: str, prior_turns: list[Turn], conv_id: str, turn_idx: int) -> Turn:
        messages = self._teacher_history(prior_turns)
        messages.append({"role": "user", "content": question})
        trace: list[Any] = []
        tools = self._ollama_tools if self._tools_active else None

        for round_i in range(self.max_tool_rounds):
            res = await self.ollama.chat(
                self.teacher_model, messages,
                think=self.include_thinking, max_tokens=self.max_tokens,
                timeout=self.teacher_timeout, tools=tools,
            )
            raw_tcs = res.get("tool_calls", []) or []
            ids = await self._next_call_ids(len(raw_tcs))
            tool_calls = [
                ToolCall(id=ids[i], name=tc["name"], arguments=tc.get("arguments", {}))
                for i, tc in enumerate(raw_tcs)
            ]
            asst = AssistantTraceMessage(
                content=res["content"],
                thinking=res["thinking"] if self.include_thinking else "",
                tool_calls=tool_calls,
            )
            trace.append(asst)

            # Echo the assistant message back into the running history.
            echo: dict[str, Any] = {"role": "assistant", "content": asst.content}
            if self.include_thinking and self.history_include_thinking and asst.thinking:
                echo["thinking"] = asst.thinking
            if tool_calls:
                echo["tool_calls"] = [
                    {"function": {"name": c.name, "arguments": c.arguments}} for c in tool_calls
                ]
            messages.append(echo)

            await self._emit(ProgressEvent(
                type="tool_call" if tool_calls else "answer", conversation_id=conv_id,
                turn=turn_idx, step=round_i + 1, answer=asst.content or None,
                thinking=asst.thinking or None,
            ))

            if not tool_calls:
                return Turn(question=question, answer=asst.content, thinking=asst.thinking, tool_trace=trace)

            # Resolve each tool call and feed results back.
            for c in tool_calls:
                result, policy, err = await self._resolve_tool_call(c)
                tm = ToolTraceMessage(tool_call_id=c.id, name=c.name, content=result)
                trace.append(tm)
                messages.append({"role": "tool", "content": result, "tool_name": c.name})
                await self._emit(ProgressEvent(
                    type="tool_result", conversation_id=conv_id, turn=turn_idx, step=round_i + 1,
                    tool_call_id=c.id, tool_name=c.name, tool_args=c.arguments,
                    tool_result=result, exec_policy=policy, tool_error=err,
                ))
            # Loop: teacher sees the tool results and continues.

        # max_tool_rounds hit: nudge a final answer without further tools.
        messages.append({"role": "system", "content": FINAL_ANSWER_NO_TOOLS})
        res = await self.ollama.chat(
            self.teacher_model, messages,
            think=self.include_thinking, max_tokens=self.max_tokens,
            timeout=self.teacher_timeout, tools=None,
        )
        asst = AssistantTraceMessage(
            content=res["content"],
            thinking=res["thinking"] if self.include_thinking else "",
            tool_calls=[],
        )
        trace.append(asst)
        await self._emit(ProgressEvent(
            type="answer", conversation_id=conv_id, turn=turn_idx,
            step=self.max_tool_rounds + 1, answer=asst.content or None,
            thinking=asst.thinking or None, message="max_tool_rounds reached",
        ))
        return Turn(question=question, answer=asst.content, thinking=asst.thinking, tool_trace=trace)

    async def _resolve_tool_call(self, call: ToolCall) -> tuple[str, str, str | None]:
        """Dispatch a tool call. Returns (result_string, exec_policy_used, error).

        - builtin: run a registered safe executor in a child process (downgraded
          to simulate if the name is not registered — never raises). The child is
          hard-killed on timeout so a runaway computation can't outlive the cap.
        - simulate: the judge acts AS the tool and returns a plausible result.
        - off: the tool is omitted from the payload; reaching here is unexpected.

        Every result string is capped via _cap_result so neither the teacher
        feedback history nor the persisted tool_trace can blow up on a large
        builtin/simulate output (the agentic-judge transcript has its own cap).
        """
        td = self._tool_by_name.get(call.name)
        if td is None:
            return _cap_result(f"[error: tool '{call.name}' is not defined]"), "off", f"undefined tool {call.name}"
        policy = td.exec_policy
        if policy == "off":
            return _cap_result("[error: tool is disabled]"), "off", "tool disabled"
        if policy == "builtin":
            fn = BUILTIN_EXECUTORS.get(td.name)
            if fn is None:
                policy = "simulate"  # downgrade, never raise
            else:
                result, err = await self._run_builtin_subprocess(
                    td.name, call.arguments, self.tool_call_timeout
                )
                return _cap_result(result), "builtin", err
        if policy == "simulate":
            try:
                result, _ = await self.judge.simulate_tool_result(
                    td, call.arguments, timeout=self.tool_call_timeout
                )
                return _cap_result(result), "simulate", None
            except JudgeError as e:
                return _cap_result(f"[error: {e}]"), "simulate", str(e)
        return _cap_result("[error: unknown exec_policy]"), "off", "unknown policy"

    async def _run_builtin_subprocess(self, fn_name: str, args: dict[str, Any], timeout: float) -> tuple[str, str | None]:
        """Run a builtin executor in a fresh child process so a timeout can
        hard-kill it (asyncio.to_thread cannot cancel a blocked thread). The
        child imports only distillery.tools_builtin (no litellm/fastapi). Returns
        (result_string, error_or_None)."""
        payload = json.dumps({"name": fn_name, "args": args})
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-c", _BUILTIN_RUNNER_SCRIPT, payload,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
        except Exception as e:  # noqa: BLE001 - spawn failure is non-fatal
            return f"[error: could not start builtin: {e}]", "spawn failed"
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            # Hard-kill the runaway process; the OS reclaims its CPU/memory.
            proc.kill()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass
            return "[error: tool timed out]", "timeout"
        except asyncio.CancelledError:
            # Session cancelled (e.g. deleted): don't leave the child running.
            proc.kill()
            raise
        out = stdout.decode("utf-8", errors="replace")
        return (out, None) if proc.returncode == 0 else (out, "builtin error")

    def _teacher_history(self, turns: list[Turn]) -> list[dict[str, Any]]:
        """Build the teacher's message history from prior turns (full trace,
        including tool calls + results; thinking gated by history_include_thinking)."""
        msgs: list[dict[str, Any]] = []
        if self.teacher_system_prompt:
            msgs.append({"role": "system", "content": self.teacher_system_prompt})
        inc = self.include_thinking and self.history_include_thinking
        for t in turns:
            msgs.append({"role": "user", "content": t.question})
            if t.tool_trace:
                for m in t.tool_trace:
                    if isinstance(m, AssistantTraceMessage):
                        a: dict[str, Any] = {"role": "assistant", "content": m.content}
                        if inc and m.thinking:
                            a["thinking"] = m.thinking
                        if m.tool_calls:
                            a["tool_calls"] = [
                                {"function": {"name": c.name, "arguments": c.arguments}}
                                for c in m.tool_calls
                            ]
                        msgs.append(a)
                    else:  # ToolTraceMessage
                        msgs.append({"role": "tool", "content": m.content, "tool_name": m.name})
            else:
                a = {"role": "assistant", "content": t.answer}
                if inc and t.thinking:
                    a["thinking"] = t.thinking
                msgs.append(a)
        return msgs

    async def _next_call_ids(self, n: int) -> list[str]:
        async with self._lock:
            ids = []
            for _ in range(n):
                ids.append(f"call_{self._call_counter}")
                self._call_counter += 1
            return ids

    # ---- helpers -------------------------------------------------------------
    def _add_usage(self, usage: dict[str, int]) -> None:
        """Judge.on_usage hook: called for every successful judge call, so
        question generation, follow-ups and grade retries are all counted.
        Synchronous (no await), so it can't interleave with other updates."""
        self.tokens["prompt"] += usage.get("prompt", 0)
        self.tokens["completion"] += usage.get("completion", 0)
        self.tokens["total"] += usage.get("total", 0)

    async def _record_error(self, msg: str) -> None:
        async with self._lock:
            self.error_count += 1
            self.last_error = msg
        await self._emit(ProgressEvent(type="error", message=msg, error_count=self.error_count))

    async def _fail(self, e: Exception) -> None:
        async with self._lock:
            self.status = "errored"
            self.last_error = str(e)
        await self._persist()

    def subscribe(self) -> asyncio.Queue[ProgressEvent]:
        """Register a client queue, pre-seeded with the events of every
        conversation still in progress so the client can render them."""
        q: asyncio.Queue[ProgressEvent] = asyncio.Queue(maxsize=512)
        for events in self._live_events.values():
            for event in events:
                _put_drop_oldest(q, event)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[ProgressEvent]) -> None:
        self._subscribers.discard(q)

    async def _emit(self, event: ProgressEvent) -> None:
        cid = event.conversation_id
        if cid:
            if event.type == "conversation_started":
                self._live_events[cid] = [event]
            elif event.type == "conversation_graded":
                self._live_events.pop(cid, None)
            elif cid in self._live_events:
                self._live_events[cid].append(event)
        for q in self._subscribers:
            _put_drop_oldest(q, event)

    async def _persist(self) -> None:
        async with self._lock:
            self.updated_at = _now_iso()
            meta = self._meta_locked()
        store.save_session(self.id, meta)

    def _meta_locked(self) -> dict:
        return {
            "id": self.id,
            "teacher_model": self.teacher_model,
            "judge_model": self.judge_model,
            "topics": self.topics,
            "seeds": self.seeds,
            "difficulty": self.difficulty,
            "target_count": self.target_count,
            "min_score": self.min_score,
            "include_thinking": self.include_thinking,
            "teacher_system_prompt": self.teacher_system_prompt,
            "grading_criteria": self.grading_criteria,
            "concurrency": self.concurrency,
            "max_tokens": self.max_tokens,
            "teacher_timeout": self.teacher_timeout,
            "judge_timeout": self.judge_timeout,
            "judge_reasoning_effort": self.judge.reasoning_effort,
            "status": self.status,
            "kept": self.kept,
            "rejected": self.rejected,
            "grade_failed": self.grade_failed,
            "error_count": self.error_count,
            "topic_counts": self.topic_counts,
            "asked": self.asked,
            "tokens": self.tokens,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            # multi-turn
            "multi_turn": self.multi_turn,
            "min_turns": self.min_turns,
            "max_turns": self.max_turns,
            "history_include_thinking": self.history_include_thinking,
            "min_turn_score": self.min_turn_score,
            "aborted": self.aborted,
            # tools (definitions only — never secrets)
            "tools": [td.model_dump() for td in self.tools],
            "tools_active": self._tools_active,
            "max_tool_rounds": self.max_tool_rounds,
            "tool_call_timeout": self.tool_call_timeout,
            "keep_partial_on_abort": self.keep_partial_on_abort,
        }

    # ---- resume -------------------------------------------------------------
    @classmethod
    def from_disk(cls, session_id: str) -> "DistillSession":
        """Rebuild a session from its session.json + raw.jsonl for resume."""
        meta = store.load_session(session_id)
        s = cls(
            teacher_model=meta["teacher_model"],
            judge_model=meta["judge_model"],
            topics=meta["topics"],
            seeds=meta.get("seeds", []),
            difficulty=meta.get("difficulty", "any"),
            target_count=meta["target_count"],
            min_score=meta["min_score"],
            include_thinking=meta.get("include_thinking", True),
            teacher_system_prompt=meta.get("teacher_system_prompt"),
            grading_criteria=meta.get("grading_criteria"),
            concurrency=meta.get("concurrency", 1),
            max_tokens=meta.get("max_tokens", 2048),
            teacher_timeout=meta.get("teacher_timeout", 180.0),
            judge_timeout=meta.get("judge_timeout", 120.0),
            judge_reasoning_effort=meta.get("judge_reasoning_effort"),
            # multi-turn
            multi_turn=meta.get("multi_turn", False),
            min_turns=meta.get("min_turns", 1),
            max_turns=meta.get("max_turns", 1),
            history_include_thinking=meta.get("history_include_thinking", True),
            min_turn_score=meta.get("min_turn_score"),
            # tools
            tools=[ToolDef(**t) for t in meta.get("tools", [])],
            max_tool_rounds=meta.get("max_tool_rounds", 6),
            tool_call_timeout=meta.get("tool_call_timeout", 60.0),
            keep_partial_on_abort=meta.get("keep_partial_on_abort", False),
            session_id=session_id,
        )
        s.status = "stopped"
        s.kept = meta.get("kept", store.count_samples(session_id))
        s.rejected = meta.get("rejected", 0)
        s.grade_failed = meta.get("grade_failed", 0)
        s.error_count = meta.get("error_count", 0)
        s.aborted = meta.get("aborted", 0)
        s.topic_counts = meta.get("topic_counts", {t: 0 for t in s.topics})
        s.asked = list(meta.get("asked", []))
        s._asked_set = {_normalize(q) for q in s.asked}
        s.tokens = meta.get("tokens", {"prompt": 0, "completion": 0, "total": 0})
        # Restore the probed capability flag so resume doesn't re-probe.
        s._tools_active = meta.get("tools_active", s._tools_active)
        s.created_at = meta.get("created_at", _now_iso())
        # Signal run() to skip the fresh-start tool probe — the capability was
        # already determined in the original run and is restored above.
        s._resumed = True
        return s