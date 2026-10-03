"""The judge: generates questions, follow-ups, and grades via LiteLLM.

LiteLLM gives us one async completion API across Anthropic, OpenAI, Groq,
OpenRouter, Ollama, etc. The teacher is always Ollama (handled separately);
the judge can be any provider, including a strong model like Claude grading
a small local model.

The judge is also used as a TOOL SIMULATOR: for tools with exec_policy
"simulate", simulate_tool_result() asks the judge to act AS the tool and return
a plausible result string (no real code, network, or filesystem access).
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

import litellm

from .prompts import (
    AGENTIC_GRADING_SYSTEM,
    AGENTIC_GRADING_USER,
    CONVERSATION_GRADING_SYSTEM,
    CONVERSATION_GRADING_USER,
    FOLLOWUP_SYSTEM,
    FOLLOWUP_USER,
    GRADING_SYSTEM,
    GRADING_USER,
    QUESTION_GEN_SYSTEM,
    QUESTION_GEN_USER,
    TEST_PROMPT,
    TOOL_SIMULATION_SYSTEM,
    TOOL_SIMULATION_USER,
)
from .schemas import Grade, ToolTraceMessage

# litellm can be chatty; keep our logs clean.
litellm.suppress_debug_info = True

# Match the done-token in either single ([DONE]) or double ([[DONE]])
# bracket form. The followup prompt asks for [[DONE]], but smaller judges
# (e.g. a local ollama llama judge) routinely emit [DONE] — if we only match
# the double-bracket form, the token leaks into the next user question and
# is asked to the teacher literally, corrupting the dataset.
_DONE_RE = re.compile(r"\[{1,2}DONE\]{1,2}", re.IGNORECASE)


class JudgeError(RuntimeError):
    pass


def _trace_used_tools(trace) -> bool:
    """True iff a turn's trace actually invoked a tool: a ToolTraceMessage is
    only ever appended when a tool is called, and a non-empty tool_calls list
    marks an assistant step that requested a tool. A non-empty trace list alone
    is NOT enough — _run_agent_turn always appends a final assistant message."""
    for m in trace or []:
        if isinstance(m, ToolTraceMessage):
            return True
        if getattr(m, "tool_calls", None):
            return True
    return False


def _extract_json(text: str) -> dict[str, Any] | None:
    """Robustly pull a JSON object out of a model response.

    Tries: full-text parse -> brace-balanced first {...} -> regex object.
    """
    if not text:
        return None
    text = text.strip()
    # Strip common code fences if present.
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)

    try:
        v = json.loads(text)
        if isinstance(v, dict):
            return v
    except json.JSONDecodeError:
        pass

    # Brace-balanced scan for the first {...} object.
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    chunk = text[start : i + 1]
                    try:
                        v = json.loads(chunk)
                        if isinstance(v, dict):
                            return v
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)

    return None


def parse_grade(text: str) -> Grade:
    raw = _extract_json(text)
    if raw is None:
        return Grade(score=0, passed=False, reasoning="parse_failed")
    try:
        score = int(raw.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(10, score))
    passed = bool(raw.get("passed", score >= 7))
    reasoning = str(raw.get("reasoning", "")).strip() or "no_reasoning"
    return Grade(score=score, passed=passed, reasoning=reasoning)


def parse_conversation_grade(text: str, n_assistant_turns: int = 0) -> Grade:
    """Like parse_grade, plus turn_scores (clamped 0-10, truncated to the
    number of assistant turns) and tool_score (None when absent)."""
    raw = _extract_json(text)
    if raw is None:
        return Grade(score=0, passed=False, reasoning="parse_failed")
    try:
        score = int(raw.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(10, score))
    passed = bool(raw.get("passed", score >= 7))
    reasoning = str(raw.get("reasoning", "")).strip() or "no_reasoning"

    raw_ts = raw.get("turn_scores") or []
    if not isinstance(raw_ts, list):
        raw_ts = []
    turn_scores: list[int] = []
    limit = n_assistant_turns or len(raw_ts)
    for ts in raw_ts[:limit]:
        try:
            turn_scores.append(max(0, min(10, int(ts))))
        except (TypeError, ValueError):
            pass

    tool_score = raw.get("tool_score")
    if tool_score is not None:
        try:
            tool_score = max(0, min(10, int(tool_score)))
        except (TypeError, ValueError):
            tool_score = None

    return Grade(
        score=score, passed=passed, reasoning=reasoning,
        turn_scores=turn_scores, tool_score=tool_score,
    )


class Judge:
    """A LiteLLM-backed judge."""

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        reasoning_effort: str | None = None,
        max_tokens: int = 2048,
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.timeout = timeout
        # Called with the usage of every successful completion (including
        # question generation, follow-ups and parse-failure retries) so the
        # owner can keep accurate token totals.
        self.on_usage: Callable[[dict[str, int]], None] | None = None
        # None / "none" -> no reasoning param sent.
        self.reasoning_effort: str | None = None
        if reasoning_effort and reasoning_effort.lower() not in ("none", ""):
            self.reasoning_effort = reasoning_effort.lower()

    # ---- low-level completion ------------------------------------------------
    async def _complete(self, messages: list[dict[str, str]], *, timeout: float | None = None) -> tuple[str, dict[str, int]]:
        """Call the judge. Returns (text, usage) with token totals."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "timeout": timeout if timeout is not None else self.timeout,
        }
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort

        # One retry on a transient error.
        last_err: Exception | None = None
        for _ in range(2):
            try:
                resp = await litellm.acompletion(**kwargs)
                text = resp.choices[0].message.content or ""
                usage = getattr(resp, "usage", None)
                usage_dict: dict[str, int] = {}
                if usage is not None:
                    usage_dict = {
                        "prompt": int(getattr(usage, "prompt_tokens", 0) or 0),
                        "completion": int(getattr(usage, "completion_tokens", 0) or 0),
                        "total": int(getattr(usage, "total_tokens", 0) or 0),
                    }
            except Exception as e:  # noqa: BLE001 - surface to caller
                last_err = e
                continue
            if self.on_usage is not None and usage_dict:
                self.on_usage(usage_dict)
            return text, usage_dict
        raise JudgeError(f"judge call failed: {last_err}")

    # ---- question generation ------------------------------------------------
    async def generate_question(
        self,
        topics: list[str],
        seeds: list[str],
        difficulty: str,
        asked: list[str],
        topic_counts: dict[str, int],
    ) -> str:
        # Pick the under-covered topic to steer toward this round.
        steer = _steer_topic(topics, topic_counts)

        user = QUESTION_GEN_USER.format(
            topics=", ".join(topics) if topics else "(any)",
            difficulty=difficulty,
            seeds="\n".join(f"- {s}" for s in seeds) if seeds else "(none)",
            asked="\n".join(f"- {q}" for q in asked[-60:]) if asked else "(none yet)",
            topic_counts=", ".join(f"{k}={v}" for k, v in topic_counts.items()) or "(none yet)",
            steer_topic=steer or "(none — vary freely)",
        )
        text, _ = await self._complete(
            [
                {"role": "system", "content": QUESTION_GEN_SYSTEM},
                {"role": "user", "content": user},
            ]
        )
        # Clean to a single line-ish question, strip stray quotes/numbering.
        q = text.strip().splitlines()
        q = [ln for ln in q if ln.strip()]
        question = " ".join(q).strip() if q else text.strip()
        question = question.strip().strip("`").strip()
        if question and question[0] in "0123456789":
            question = re.sub(r"^\s*\d+[.):]\s*", "", question)
        return question.strip().strip('"').strip()

    # ---- follow-up generation (multi-turn) ---------------------------------
    async def generate_followup(
        self,
        topics: list[str],
        transcript: list,
        turn_count: int,
        min_turns: int,
        max_turns: int,
        can_done: bool,
        *,
        extra_strict: bool = False,
    ) -> str | None:
        """Ask the judge for ONE probing follow-up. Returns the question, or
        None when the judge emits [[DONE]] (honored only if can_done=True)."""
        can_done_line = (
            "When the conversation has naturally concluded and there is nothing "
            "more worth probing, you may output ONLY the token [[DONE]] instead "
            "of a question."
            if can_done
            else "You MUST ask a follow-up question; do NOT signal [[DONE]] (the "
            "minimum turn count has not been met)."
        )
        done_clause = " OR the token [[DONE]]" if can_done else ""
        transcript_text = "\n\n".join(
            f"Turn {i + 1} — Q: {t.question}\nA: {t.answer}"
            for i, t in enumerate(transcript)
        )
        user = FOLLOWUP_USER.format(
            topics=", ".join(topics) if topics else "(any)",
            transcript=transcript_text or "(none yet)",
            turn_count=turn_count,
            min_turns=min_turns,
            max_turns=max_turns,
            next_turn=turn_count + 1,
            done_clause=done_clause,
        )
        system = FOLLOWUP_SYSTEM.format(can_done_line=can_done_line)
        if extra_strict:
            system += (
                "\n\nIMPORTANT: You must ask a follow-up question now. Do "
                "not signal done and do not refuse."
            )
        text, _ = await self._complete([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        return _parse_followup(text, can_done)

    # ---- grading ------------------------------------------------------------
    async def grade(self, question: str, answer: str, criteria: str | None) -> tuple[Grade, dict[str, int]]:
        user = GRADING_USER.format(
            question=question,
            answer=answer,
            criteria_line=f"Additional criteria: {criteria}" if criteria else "",
        )
        text, usage = await self._complete(
            [
                {"role": "system", "content": GRADING_SYSTEM},
                {"role": "user", "content": user},
            ]
        )
        grade = parse_grade(text)
        if grade.reasoning == "parse_failed":
            # One retry with a firmer instruction, keeping the same inputs.
            text, usage = await self._complete(
                [
                    {"role": "system", "content": GRADING_SYSTEM + "\n\nIMPORTANT: Return ONLY the JSON object, no other text."},
                    {"role": "user", "content": user},
                ]
            )
            grade = parse_grade(text)
        return grade, usage

    async def grade_conversation(
        self,
        transcript: list,
        criteria: str | None,
        tools_summary: str | None = None,
    ) -> tuple[Grade, dict[str, int]]:
        """Whole-conversation grade. `transcript` is a list of Turn-like objects
        with .question/.answer/.tool_trace. Selects the AGENTIC prompt iff tools
        were actually USED (a ToolTraceMessage or a non-empty tool_calls list in
        some turn's trace) — NOT merely available. _run_agent_turn always appends
        a final assistant message to the trace, so a non-empty tool_trace list
        alone is not evidence of tool use. Otherwise the plain multi-turn
        CONVERSATION_GRADING prompt runs byte-identical."""
        used_tools = tools_summary is not None and any(
            _trace_used_tools(getattr(t, "tool_trace", None)) for t in transcript
        )
        n = len(transcript)
        if used_tools:
            return await self._grade_agentic(transcript, criteria, tools_summary or "", n)
        return await self._grade_conversation_plain(transcript, criteria, n)

    async def _grade_conversation_plain(
        self, transcript: list, criteria: str | None, n: int,
    ) -> tuple[Grade, dict[str, int]]:
        transcript_text = "\n\n".join(
            f"[Turn {i + 1}]\nUser: {t.question}\nAssistant: {t.answer}"
            for i, t in enumerate(transcript)
        )
        user = CONVERSATION_GRADING_USER.format(
            n_turns=n,
            transcript=transcript_text,
            criteria_line=f"Additional criteria: {criteria}" if criteria else "",
        )
        messages = [
            {"role": "system", "content": CONVERSATION_GRADING_SYSTEM},
            {"role": "user", "content": user},
        ]
        text, usage = await self._complete(messages)
        grade = parse_conversation_grade(text, n)
        if grade.reasoning == "parse_failed":
            text, usage = await self._complete([
                {"role": "system", "content": CONVERSATION_GRADING_SYSTEM
                    + "\n\nIMPORTANT: Return ONLY the JSON object, no other text."},
                {"role": "user", "content": user},
            ])
            grade = parse_conversation_grade(text, n)
        return grade, usage

    async def _grade_agentic(
        self, transcript: list, criteria: str | None, tools_summary: str, n: int,
    ) -> tuple[Grade, dict[str, int]]:
        transcript_text = _render_agentic_transcript(transcript)
        user = AGENTIC_GRADING_USER.format(
            tools_summary=tools_summary,
            transcript=transcript_text,
            criteria_line=f"Additional criteria: {criteria}" if criteria else "",
        )
        messages = [
            {"role": "system", "content": AGENTIC_GRADING_SYSTEM},
            {"role": "user", "content": user},
        ]
        text, usage = await self._complete(messages)
        grade = parse_conversation_grade(text, n)
        if grade.reasoning == "parse_failed":
            text, usage = await self._complete([
                {"role": "system", "content": AGENTIC_GRADING_SYSTEM
                    + "\n\nIMPORTANT: Return ONLY the JSON object, no other text."},
                {"role": "user", "content": user},
            ])
            grade = parse_conversation_grade(text, n)
        return grade, usage

    # ---- tool simulation (default exec path) -------------------------------
    async def simulate_tool_result(
        self, tool_def, arguments: dict[str, Any], *, timeout: float | None = None,
    ) -> tuple[str, dict[str, int]]:
        user = TOOL_SIMULATION_USER.format(
            tool_name=tool_def.name,
            tool_description=tool_def.description,
            parameters=json.dumps(tool_def.parameters, ensure_ascii=False),
            arguments=json.dumps(arguments, ensure_ascii=False),
        )
        text, usage = await self._complete(
            [
                {"role": "system", "content": TOOL_SIMULATION_SYSTEM},
                {"role": "user", "content": user},
            ],
            timeout=timeout,
        )
        return text.strip(), usage

    # ---- connectivity test ---------------------------------------------------
    async def test(self) -> bool:
        try:
            text, _ = await self._complete([{"role": "user", "content": TEST_PROMPT}])
            return bool(text.strip())
        except Exception:
            return False


def _parse_followup(text: str, can_done: bool) -> str | None:
    """Strip [[DONE]], apply the same line-join/quote/numbering cleanup as
    generate_question. Return the cleaned question, or None for DONE/empty."""
    if not text:
        return None
    if can_done and _DONE_RE.search(text):
        return None
    text = _DONE_RE.sub("", text)
    q = text.strip().splitlines()
    q = [ln for ln in q if ln.strip()]
    question = " ".join(q).strip() if q else text.strip()
    question = question.strip().strip("`").strip()
    if question and question[0] in "0123456789":
        question = re.sub(r"^\s*\d+[.):]\s*", "", question)
    question = question.strip().strip('"').strip()
    return question or None


def _render_agentic_transcript(transcript: list, budget: int = 12000) -> str:
    """Render turns as text for the agentic judge. Truncate long tool-result
    bodies (500 chars) and, if still over budget, progressively shorten oldest
    tool-result bodies (replace with '[dropped]') until under budget. Keeps all
    call names, arguments, and final answers."""

    def render_tool_result(body: str, cap: int) -> str:
        if len(body) <= cap:
            return body
        return body[:cap] + " [result truncated]" if cap > 0 else "[dropped]"

    # Collect rendered entries with enough structure to re-cap tool results.
    # Each entry: (kind, turn_idx, order_idx, text). kind == "tool" can be re-cut.
    entries: list[tuple[str, int, int, str, object]] = []
    for ti, t in enumerate(transcript):
        entries.append(("turn", ti, 0, f"--- Turn {ti + 1} ---", None))
        entries.append(("user", ti, 0, f"User: {t.question}", None))
        oi = 0
        for m in t.tool_trace:
            if hasattr(m, "tool_calls"):  # AssistantTraceMessage
                if m.tool_calls:
                    calls = ", ".join(c.name for c in m.tool_calls)
                    entries.append(("asst", ti, oi, f"Assistant (called tools: {calls}): {m.content}", None))
                else:
                    entries.append(("asst", ti, oi, f"Assistant: {m.content}", None))  # final
            else:  # ToolTraceMessage — keep a ref so we can re-cap its body
                entries.append(("tool", ti, oi, f"Tool {m.name}: {render_tool_result(m.content, 500)}", m))
            oi += 1

    def joined() -> str:
        return "\n".join(e[3] for e in entries)

    full = joined()
    if len(full) <= budget:
        return full
    # Progressively shorten oldest tool-result bodies, then drop them entirely.
    for cap in (200, 60, 0):
        for e in entries:
            if e[0] != "tool" or e[4] is None:
                continue
            if len(full) <= budget:
                return full
            m = e[4]
            new = f"Tool {m.name}: {render_tool_result(m.content, cap)}"
            entries[entries.index(e)] = (e[0], e[1], e[2], new, e[4])
            full = joined()
        if len(full) <= budget:
            return full
    return full[:budget] + "\n[transcript truncated]"


def _steer_topic(topics: list[str], topic_counts: dict[str, int]) -> str | None:
    """Return the topic with the fewest kept samples (ties -> first)."""
    if not topics:
        return None
    return min(topics, key=lambda t: topic_counts.get(t, 0))