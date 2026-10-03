"""Registry of active distillation sessions + on-disk history.

Active sessions live in-memory (id -> DistillSession). Past sessions are
discovered by scanning datasets/*/session.json. The registry also tracks the
asyncio task for each running session so it isn't garbage-collected.
"""
from __future__ import annotations

import asyncio
from typing import Iterator

from .distiller import DistillSession
from .schemas import SessionMeta
from .store import store


def disk_status(meta: dict) -> str:
    """Status of a session that isn't active in this process. One saved as
    "running" was interrupted (server stopped or crashed mid-run), so report
    it as "stopped": that's what lets the UI offer Resume instead of View."""
    status = meta.get("status", "stopped")
    return "stopped" if status == "running" else status


class SessionRegistry:
    def __init__(self) -> None:
        self._active: dict[str, DistillSession] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    # ---- active lifecycle ---------------------------------------------------
    def create(self, session: DistillSession) -> None:
        self._active[session.id] = session

    def start(self, session: DistillSession) -> None:
        self.create(session)
        self._tasks[session.id] = asyncio.create_task(self._run(session))

    async def _run(self, session: DistillSession) -> None:
        try:
            await session.run()
        except Exception:  # noqa: BLE001 - session.run handles its own errors
            pass
        finally:
            # Keep the session object around after completion for status reads,
            # but drop the task ref.
            self._tasks.pop(session.id, None)

    def get(self, session_id: str) -> DistillSession | None:
        return self._active.get(session_id)

    def stop(self, session_id: str) -> bool:
        s = self._active.get(session_id)
        if s and s.status == "running":
            s.stop()
            return True
        return False

    async def delete(self, session_id: str) -> bool:
        """Stop + forget an active session and wipe its on-disk directory.
        Cancelling the live task (rather than just stop()) means the run loop
        never reaches its final _persist, and waiting for it (run() also
        cancels its producer/workers) guarantees nothing is still writing when
        the directory is removed. Returns True if anything was on disk to remove.
        Raises StoreError for an invalid session id."""
        store.validate_id(session_id)
        self._active.pop(session_id, None)
        task = self._tasks.pop(session_id, None)
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return store.delete_session(session_id)

    # ---- listing ------------------------------------------------------------
    def list_metas(self) -> list[SessionMeta]:
        """Merge active + on-disk sessions into SessionMeta rows."""
        metas: list[SessionMeta] = []
        seen: set[str] = set()

        # Active first (live counts).
        for s in self._active.values():
            seen.add(s.id)
            metas.append(self._meta_from_session(s))

        # On-disk history.
        for m in store.list_sessions():
            if m["id"] in seen:
                continue
            metas.append(
                SessionMeta(
                    id=m["id"],
                    teacher_model=m.get("teacher_model", ""),
                    judge_model=m.get("judge_model", ""),
                    topics=m.get("topics", []),
                    status=disk_status(m),
                    target_count=m.get("target_count", 0),
                    kept=m.get("kept", 0),
                    rejected=m.get("rejected", 0),
                    grade_failed=m.get("grade_failed", 0),
                    error_count=m.get("error_count", 0),
                    multi_turn=m.get("multi_turn", False),
                    min_turns=m.get("min_turns", 1),
                    max_turns=m.get("max_turns", 1),
                    tools_active=m.get("tools_active", False),
                    created_at=m.get("created_at"),
                    updated_at=m.get("updated_at"),
                )
            )
        return metas

    def _meta_from_session(self, s: DistillSession) -> SessionMeta:
        return SessionMeta(
            id=s.id,
            teacher_model=s.teacher_model,
            judge_model=s.judge_model,
            topics=s.topics,
            status=s.status,
            target_count=s.target_count,
            kept=s.kept,
            rejected=s.rejected,
            grade_failed=s.grade_failed,
            error_count=s.error_count,
            multi_turn=s.multi_turn,
            min_turns=s.min_turns,
            max_turns=s.max_turns,
            tools_active=s._tools_active,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )

    # ---- resume -------------------------------------------------------------
    def resume(self, session_id: str) -> DistillSession | None:
        """Rebuild a finished/errored session from disk and continue it."""
        existing = self._active.get(session_id)
        if existing and existing.status == "running":
            return existing  # already running, nothing to do
        try:
            session = DistillSession.from_disk(session_id)
        except Exception:
            return None
        if session.kept >= session.target_count:
            return session  # already complete; just return as-is
        if existing is not None:
            # The judge API key is never written to disk; carry over the one
            # this session was started with so resume doesn't silently fall
            # back to the key from the environment.
            session.judge.api_key = existing.judge.api_key
        self.start(session)
        return session


registry = SessionRegistry()