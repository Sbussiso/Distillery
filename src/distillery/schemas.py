"""Pydantic schemas: API request/response bodies and internal records.

The trace model is UNIFIED across single-turn, multi-turn, and tool-calling
(agentic) distillation:

- A session produces Samples. A Sample is one kept unit (one grade, one keep
  decision). For single-turn it is one Q/A; for multi-turn it is a conversation
  of Turns; for agentic, each Turn may carry a `tool_trace` of intermediate
  assistant(tool_calls) and tool(result) messages.
- All new fields default to empty/None, so legacy single-turn rows parse and
  re-serialize byte-identically (store._raw_obj drops the empty new keys).
"""
from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, Field, model_validator

from .config import settings


# --------------------------------------------------------------------------
# Tool definition (config; persisted in session.json; never carries secrets)
# --------------------------------------------------------------------------
class ToolDef(BaseModel):
    name: str = Field(..., pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    description: str = Field(..., min_length=1)
    parameters: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )
    # "simulate" = LLM produces a plausible result (default; always safe)
    # "builtin"  = run a registered safe executor matched by name (calculator)
    # "off"      = omit from the Ollama tools payload entirely (clean disable)
    exec_policy: Literal["simulate", "builtin", "off"] = "simulate"


class ToolSpec(BaseModel):
    """A tool as sent to Ollama and written into the export system message."""
    type: Literal["function"] = "function"
    function: dict[str, Any]  # {"name","description","parameters"}


# --------------------------------------------------------------------------
# Trace messages: typed union for lossless, ordered export
# --------------------------------------------------------------------------
class ToolCall(BaseModel):
    id: str  # "call_N", assigned once at capture, persisted, never recomputed
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class AssistantTraceMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str = ""
    thinking: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)


class ToolTraceMessage(BaseModel):
    role: Literal["tool"] = "tool"
    tool_call_id: str
    name: str
    content: str  # result string, capped at the source in _resolve_tool_call


TraceMessage = Union[AssistantTraceMessage, ToolTraceMessage]


# --------------------------------------------------------------------------
# External API request models
# --------------------------------------------------------------------------
class DistillRequest(BaseModel):
    teacher_model: str = Field(..., description="Ollama model being distilled, e.g. 'qwen3:8b'")
    judge_model: str = Field(..., description="LiteLLM model string, e.g. 'anthropic/claude-opus-5' or 'ollama/llama3.1:8b'")
    judge_api_key: str | None = Field(None, description="Optional API key override; else read from env")
    judge_reasoning_effort: Literal["none", "low", "medium", "high"] | None = Field(
        None, description="Enable judge thinking. 'none'/'None' disables it."
    )

    topics: list[str] = Field(..., min_length=1, description="Domains the questions should cover")
    seeds: list[str] = Field(default_factory=list, description="Optional example questions to vary around")
    difficulty: Literal["any", "easy", "medium", "hard"] = "any"

    target_count: int = Field(10, ge=1, le=10000, description="Number of accepted samples to collect")
    min_score: int = Field(7, ge=1, le=10, description="Minimum grade (1-10) to keep an answer")
    include_thinking: bool = Field(True, description="Capture teacher thinking when present")

    teacher_system_prompt: str | None = None
    grading_criteria: str | None = None

    concurrency: int = Field(1, ge=1, le=16, description="Parallel answer/grade workers")
    max_tokens: int = Field(default_factory=lambda: settings.default_max_tokens, ge=32, le=32768)
    teacher_timeout: float = Field(180.0, ge=5.0, le=3600.0)
    judge_timeout: float = Field(120.0, ge=5.0, le=3600.0)

    # --- multi-turn ---
    multi_turn: bool = Field(False, description="Enable multi-turn conversations")
    min_turns: int = Field(1, ge=1, le=20, description="Min turns per conversation (multi-turn only)")
    max_turns: int = Field(1, ge=1, le=20, description="Max turns per conversation (multi-turn only)")
    history_include_thinking: bool = Field(
        True, description="Feed prior assistant thinking back into teacher history (multi-turn)"
    )
    min_turn_score: int | None = Field(
        None, ge=1, le=10,
        description="Opt-in per-turn veto: reject conversation if any turn_score < this",
    )

    # --- tools / agents ---
    tools: list[ToolDef] = Field(default_factory=list, description="Tools the teacher may call")
    max_tool_rounds: int = Field(6, ge=1, le=20, description="Inner agent-loop cap per turn")
    tool_call_timeout: float = Field(60.0, ge=5.0, le=600.0, description="Per-tool-call timeout (builtin or simulate)")
    keep_partial_on_abort: bool = Field(
        False, description="On agent-loop abort, keep completed turns and grade them"
    )

    @model_validator(mode="after")
    def _validate_turns(self) -> "DistillRequest":
        if not self.multi_turn:
            # Force single-turn: ignore whatever the client sent.
            self.min_turns = 1
            self.max_turns = 1
        else:
            if not (1 <= self.min_turns <= self.max_turns):
                raise ValueError("require 1 <= min_turns <= max_turns")
        return self


class JudgeTestRequest(BaseModel):
    model: str
    api_key: str | None = None
    reasoning_effort: Literal["none", "low", "medium", "high"] | None = None


class ToolSimulateRequest(BaseModel):
    tool_name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    arguments: dict[str, Any] = Field(default_factory=dict)
    judge_model: str
    judge_api_key: str | None = None
    judge_reasoning_effort: str | None = None


# --------------------------------------------------------------------------
# External API response models
# --------------------------------------------------------------------------
class OllamaModel(BaseModel):
    name: str
    size: int | None = None
    param_size: str | None = None
    quant: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    thinking: bool = False


class HealthStatus(BaseModel):
    ok: bool
    detail: str | None = None


class JudgeProvider(BaseModel):
    provider: str
    label: str
    models: list[str]


class Grade(BaseModel):
    score: int  # 1-10 (0 = parse failed)
    passed: bool
    reasoning: str
    # Multi-turn: one score per assistant turn (empty for single-turn).
    turn_scores: list[int] = Field(default_factory=list)
    # Agentic: informational sub-score for tool use (None when no tools used).
    tool_score: int | None = None


class Turn(BaseModel):
    """One turn of a conversation. For agentic turns, `tool_trace` holds the
    ordered intermediate assistant(tool_calls)+tool(result) messages; the
    turn's `answer`/`thinking` mirror the final assistant message."""
    question: str
    answer: str = ""
    thinking: str = ""
    tool_trace: list[TraceMessage] = Field(default_factory=list)

    @model_validator(mode="after")
    def _derive_flat_from_trace(self) -> "Turn":
        # When a tool trace exists and no explicit answer was set, derive the
        # answer/thinking from the last assistant message that had no tool
        # calls (the terminal/final-answer message). No-op when tool_trace is
        # empty (the no-tools path sets answer/thinking directly).
        if self.tool_trace and not self.answer:
            for m in reversed(self.tool_trace):
                if isinstance(m, AssistantTraceMessage) and not m.tool_calls:
                    self.answer = m.content
                    self.thinking = m.thinking
                    break
        return self


class Sample(BaseModel):
    question: str
    answer: str
    thinking: str = ""
    score: int
    passed: bool
    judge_reasoning: str
    teacher_model: str
    judge_model: str
    topics: list[str]
    difficulty: str | None
    timestamp: str

    # --- multi-turn ---
    turns: list[Turn] = Field(default_factory=list)
    conversation_id: str | None = None
    n_turns: int = 1
    # --- tools ---
    tools: list[ToolSpec] | None = None      # None => no system+tools msg in export
    system_prompt: str | None = None          # teacher system prompt (tools samples)
    turn_scores: list[int] | None = None
    tool_score: int | None = None

    @model_validator(mode="after")
    def _mirror_turn0(self) -> "Sample":
        # When turns is non-empty, flat fields mirror turn-0 so the existing
        # UI / samples page / alpaca export / asked-set rebuild work unchanged.
        if self.turns and not self.answer:
            t0 = self.turns[0]
            self.answer = t0.answer
            self.thinking = t0.thinking
        if self.turns:
            self.n_turns = len(self.turns)
        return self


class TokenTotals(BaseModel):
    prompt: int = 0
    completion: int = 0
    total: int = 0


class SessionStatus(BaseModel):
    id: str
    teacher_model: str
    judge_model: str
    topics: list[str]
    status: Literal["running", "stopped", "completed", "errored"]
    target_count: int
    kept: int
    rejected: int
    grade_failed: int
    error_count: int
    topic_counts: dict[str, int]
    tokens: TokenTotals
    # multi-turn
    multi_turn: bool = False
    min_turns: int = 1
    max_turns: int = 1
    aborted: int = 0
    # tools
    tools_active: bool = False
    last_question: str | None = None
    last_answer: str | None = None
    last_thinking: str | None = None
    last_grade: Grade | None = None
    last_error: str | None = None


class SessionMeta(BaseModel):
    """Lightweight row for the sessions list (on-disk + active)."""
    id: str
    teacher_model: str
    judge_model: str
    topics: list[str]
    status: str
    target_count: int
    kept: int
    rejected: int
    grade_failed: int
    error_count: int
    multi_turn: bool = False
    min_turns: int = 1
    max_turns: int = 1
    tools_active: bool = False
    created_at: str | None = None
    updated_at: str | None = None


class DistillStarted(BaseModel):
    session_id: str


class SamplesPage(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[Sample]


class ToolSimulateResult(BaseModel):
    result: str
    ok: bool = True
    error: str | None = None


# --------------------------------------------------------------------------
# Internal progress event (streamed over the WebSocket)
# --------------------------------------------------------------------------
class ProgressEvent(BaseModel):
    type: Literal[
        "question",
        "answer",
        "grade",
        "kept",
        "rejected",
        "grade_failed",
        "error",
        "complete",
        "stopped",
        "status",
        # multi-turn
        "conversation_started",
        "turn_answer",
        "turn_followup",
        "conversation_graded",
        "conversation_aborted",
        # tools
        "tool_call",
        "tool_result",
        "tool_unsupported",
    ] = "status"
    # Populated per type; absent fields are simply None.
    question: str | None = None
    answer: str | None = None
    thinking: str | None = None
    grade: Grade | None = None
    kept: int | None = None
    rejected: int | None = None
    grade_failed: int | None = None
    error_count: int | None = None
    aborted: int | None = None
    target: int | None = None
    topic: str | None = None
    message: str | None = None
    status: SessionStatus | None = None
    # multi-turn
    conversation_id: str | None = None
    turn: int | None = None
    turn_count: int | None = None
    # tools
    step: int | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    tool_result: str | None = None
    exec_policy: str | None = None
    tool_error: str | None = None
    tools_active: bool | None = None