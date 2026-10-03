"""FastAPI routes: Ollama, judges, distillation CRUD, WebSocket stream, export."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from ..config import settings
from ..distiller import DistillSession
from ..ollama import ollama_client
from ..schemas import (
    DistillRequest,
    DistillStarted,
    HealthStatus,
    JudgeProvider,
    JudgeTestRequest,
    OllamaModel,
    SamplesPage,
    SessionMeta,
    SessionStatus,
    ToolSimulateRequest,
    ToolSimulateResult,
)
from ..sessions import registry
from ..store import StoreError, store

router = APIRouter(prefix="/api")

# Curated judge provider/model suggestions. The model field is free-text in the
# UI; these are just convenient starting points.
_JUDGE_PROVIDERS = [
    JudgeProvider(
        provider="anthropic",
        label="Anthropic (Claude)",
        models=["anthropic/claude-opus-5", "anthropic/claude-sonnet-5", "anthropic/claude-haiku-4-5"],
    ),
    JudgeProvider(provider="openai", label="OpenAI", models=["openai/gpt-4o", "openai/gpt-4o-mini"]),
    JudgeProvider(provider="groq", label="Groq (fast)", models=["groq/llama-3.3-70b-versatile"]),
    JudgeProvider(provider="openrouter", label="OpenRouter", models=["openrouter/anthropic/claude-3.5-sonnet"]),
    JudgeProvider(provider="ollama", label="Ollama (local, free)", models=["ollama/llama3.1:8b", "ollama/qwen3:32b"]),
]


# --------------------------------------------------------------------------
# Ollama
# --------------------------------------------------------------------------
@router.get("/ollama/health", response_model=HealthStatus)
async def ollama_health() -> HealthStatus:
    ok = await ollama_client.health()
    return HealthStatus(ok=ok, detail=None if ok else f"Ollama not reachable at {settings.ollama_base_url}")


@router.get("/ollama/models", response_model=list[OllamaModel])
async def ollama_models() -> list[OllamaModel]:
    try:
        return await ollama_client.list_models()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"failed to list Ollama models: {e}") from e


# --------------------------------------------------------------------------
# Judges
# --------------------------------------------------------------------------
@router.get("/judges/providers", response_model=list[JudgeProvider])
async def judge_providers() -> list[JudgeProvider]:
    return _JUDGE_PROVIDERS


@router.post("/judges/test", response_model=HealthStatus)
async def judge_test(req: JudgeTestRequest) -> HealthStatus:
    from ..judge import Judge

    j = Judge(req.model, api_key=req.api_key, reasoning_effort=req.reasoning_effort, timeout=30.0)
    ok = await j.test()
    return HealthStatus(ok=ok, detail=None if ok else "judge call failed (check model string + API key)")


# --------------------------------------------------------------------------
# Tools (presets + simulation test)
# --------------------------------------------------------------------------
_TOOL_PRESETS = [
    {
        "name": "calculator",
        "description": "Evaluate a safe arithmetic expression. Supports + - * / // % ** and the constants pi, e, tau.",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "The arithmetic expression to evaluate, e.g. '2+2*3' or 'sin(pi/2)' (sin not supported; use pi/e/tau)."}
            },
            "required": ["expression"],
        },
        "exec_policy": "builtin",
    },
    {
        "name": "search",
        "description": "Search a knowledge base for documents matching a query. Returns up to 3 short snippets.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
                "top_k": {"type": "integer", "description": "Number of results to return (1-5).", "default": 3},
            },
            "required": ["query"],
        },
        "exec_policy": "simulate",
    },
    {
        "name": "lookup_user",
        "description": "Look up a user profile by username. Returns a JSON-ish profile string.",
        "parameters": {
            "type": "object",
            "properties": {
                "username": {"type": "string", "description": "The username to look up."},
            },
            "required": ["username"],
        },
        "exec_policy": "simulate",
    },
]


@router.get("/tools/presets")
async def tool_presets() -> list[dict]:
    """Reusable tool definitions the UI can add with one click."""
    return _TOOL_PRESETS


@router.post("/tools/simulate", response_model=ToolSimulateResult)
async def tools_simulate(req: ToolSimulateRequest) -> ToolSimulateResult:
    """Test what the judge-as-tool-simulator would return for given arguments.

    Builtin-policy tools are not executed here (no safe executor wired into the
    HTTP path); this endpoint always uses the simulate path so the user can
    preview a simulated result without running a full session.
    """
    from ..judge import Judge
    from ..schemas import ToolDef

    td = ToolDef(name=req.tool_name, description=req.description, parameters=req.parameters, exec_policy="simulate")
    j = Judge(req.judge_model, api_key=req.judge_api_key, reasoning_effort=req.judge_reasoning_effort, timeout=60.0)
    try:
        result, _ = await j.simulate_tool_result(td, req.arguments)
        return ToolSimulateResult(result=result, ok=True)
    except Exception as e:
        return ToolSimulateResult(result="", ok=False, error=str(e))


# --------------------------------------------------------------------------
# Distillation
# --------------------------------------------------------------------------
@router.post("/distill", response_model=DistillStarted)
async def start_distill(req: DistillRequest) -> DistillStarted:
    # Reject a start if Ollama is down so the user gets a clear error up front.
    if not await ollama_client.health():
        raise HTTPException(status_code=502, detail=f"Ollama not reachable at {settings.ollama_base_url}")
    session = DistillSession(
        teacher_model=req.teacher_model,
        judge_model=req.judge_model,
        judge_api_key=req.judge_api_key,
        judge_reasoning_effort=req.judge_reasoning_effort,
        topics=req.topics,
        seeds=req.seeds,
        difficulty=req.difficulty,
        target_count=req.target_count,
        min_score=req.min_score,
        include_thinking=req.include_thinking,
        teacher_system_prompt=req.teacher_system_prompt,
        grading_criteria=req.grading_criteria,
        concurrency=req.concurrency,
        max_tokens=req.max_tokens,
        teacher_timeout=req.teacher_timeout,
        judge_timeout=req.judge_timeout,
        # multi-turn
        multi_turn=req.multi_turn,
        min_turns=req.min_turns,
        max_turns=req.max_turns,
        history_include_thinking=req.history_include_thinking,
        min_turn_score=req.min_turn_score,
        # tools
        tools=req.tools,
        max_tool_rounds=req.max_tool_rounds,
        tool_call_timeout=req.tool_call_timeout,
        keep_partial_on_abort=req.keep_partial_on_abort,
    )
    registry.start(session)
    return DistillStarted(session_id=session.id)


@router.get("/distill/sessions", response_model=list[SessionMeta])
async def list_sessions() -> list[SessionMeta]:
    return registry.list_metas()


@router.get("/distill/{session_id}", response_model=SessionStatus)
async def get_session(session_id: str) -> SessionStatus:
    s = registry.get(session_id)
    if s is not None:
        return s.status_obj()
    # Maybe a finished on-disk session; reconstruct read-only status.
    try:
        meta = store.load_session(session_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found") from e
    from ..schemas import TokenTotals

    return SessionStatus(
        id=meta["id"],
        teacher_model=meta["teacher_model"],
        judge_model=meta["judge_model"],
        topics=meta.get("topics", []),
        status=meta.get("status", "stopped"),  # type: ignore[arg-type]
        target_count=meta.get("target_count", 0),
        kept=meta.get("kept", 0),
        rejected=meta.get("rejected", 0),
        grade_failed=meta.get("grade_failed", 0),
        error_count=meta.get("error_count", 0),
        topic_counts=meta.get("topic_counts", {}),
        tokens=TokenTotals(**meta.get("tokens", {"prompt": 0, "completion": 0, "total": 0})),
        multi_turn=meta.get("multi_turn", False),
        min_turns=meta.get("min_turns", 1),
        max_turns=meta.get("max_turns", 1),
        aborted=meta.get("aborted", 0),
        tools_active=meta.get("tools_active", False),
    )


@router.post("/distill/{session_id}/stop", response_model=SessionStatus)
async def stop_session(session_id: str) -> SessionStatus:
    registry.stop(session_id)
    s = registry.get(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"session {session_id} not active")
    return s.status_obj()


@router.post("/distill/{session_id}/resume", response_model=DistillStarted)
async def resume_session(session_id: str) -> DistillStarted:
    s = registry.resume(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found on disk")
    return DistillStarted(session_id=s.id)


@router.delete("/distill/{session_id}")
async def delete_session(session_id: str) -> dict:
    """Delete a session (active or on-disk). Cancels the live task first so a
    mid-run persist can't recreate the directory."""
    try:
        deleted = await registry.delete(session_id)
    except StoreError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not deleted:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    return {"ok": True}


@router.get("/distill/{session_id}/samples", response_model=SamplesPage)
async def get_samples(
    session_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
) -> SamplesPage:
    try:
        total, items = store.get_samples(session_id, offset, limit)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return SamplesPage(total=total, offset=offset, limit=limit, items=items)


@router.get("/distill/{session_id}/export")
async def export_dataset(
    session_id: str,
    fmt: str = Query("sharegpt", pattern="^(sharegpt|raw|alpaca)$"),
    include_thinking: bool = Query(True),
    thinking_format: str = Query("separate_field", pattern="^(separate_field|inline_tags|strip)$"),
    include_tools_spec: bool = Query(True),
):
    try:
        path = store.export_path(session_id, fmt, include_thinking, thinking_format, include_tools_spec)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    if not path.exists():
        raise HTTPException(status_code=404, detail="dataset not found")
    media = "application/jsonl"
    fname = f"{session_id}_{path.name}"
    return FileResponse(str(path), media_type=media, filename=fname)


# --------------------------------------------------------------------------
# WebSocket: live progress
# --------------------------------------------------------------------------
@router.websocket("/distill/{session_id}/stream")
async def distill_stream(ws: WebSocket, session_id: str) -> None:
    await ws.accept()
    s = registry.get(session_id)
    if s is None:
        await ws.send_text(json.dumps({"type": "error", "message": "session not active"}))
        await ws.close()
        return

    # Subscribe before the snapshot so no event falls between the two. Each
    # client gets its own queue (pre-seeded with in-flight conversations).
    events = s.subscribe()
    try:
        await ws.send_text(json.dumps({"type": "status", "status": s.status_obj().model_dump(mode="json")}))

        while True:
            # Drain events as they arrive; bail when the session is done.
            try:
                event = await asyncio.wait_for(events.get(), timeout=1.0)
            except asyncio.TimeoutError:
                if s.status != "running":
                    break
                continue
            await ws.send_text(event.model_dump_json())
            if event.type in ("complete", "stopped"):
                break
    except WebSocketDisconnect:
        pass
    finally:
        s.unsubscribe(events)
        try:
            await ws.close()
        except Exception:
            pass