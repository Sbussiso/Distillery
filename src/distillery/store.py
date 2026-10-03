"""On-disk dataset + session persistence.

Layout per session, under {datasets_dir}/{session_id}/:
    raw.jsonl       - full sample records (one JSON per line), the source of truth
    sharegpt.jsonl  - {"messages":[...]}  (with thinking on assistant turns)
    alpaca.jsonl    - {instruction, output, thinking, grade, ...markers}
    session.json    - config + counts + asked-set + status (rewritten each round)

The raw.jsonl is the source of truth and holds the full unified trace model
(turns + tool_trace). sharegpt.jsonl / alpaca.jsonl are convenience projections
written with default thinking flags at append time; export_path() rebuilds
sharegpt on demand to honour include_thinking / thinking_format / tools.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterator

from .config import settings
from .schemas import AssistantTraceMessage, Sample

RAW = "raw.jsonl"
SHAREGPT = "sharegpt.jsonl"
ALPACA = "alpaca.jsonl"
SESSION = "session.json"

_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"

# Session ids are generated as uuid hex; anything else (".", "..", separators)
# must never be joined onto the datasets root.
_SESSION_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


class StoreError(RuntimeError):
    pass


class Store:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or settings.datasets_path

    # ---- paths --------------------------------------------------------------
    @staticmethod
    def validate_id(session_id: str) -> None:
        if not _SESSION_ID_RE.fullmatch(session_id):
            raise StoreError(f"invalid session id {session_id!r}")

    def _dir(self, session_id: str) -> Path:
        self.validate_id(session_id)
        return self.root / session_id

    def session_dir(self, session_id: str) -> Path:
        d = self._dir(session_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ---- sample append ------------------------------------------------------
    def append_sample(self, session_id: str, sample: Sample) -> None:
        d = self.session_dir(session_id)

        # raw.jsonl: source of truth, full unified trace (byte-identical to
        # legacy single-turn shape when the new fields are empty/None).
        _append_jsonl(d / RAW, _raw_obj(sample))

        # sharegpt.jsonl: convenience projection with default thinking flags.
        _append_jsonl(d / SHAREGPT, _build_sharegpt(sample, include_thinking=True, thinking_format="separate_field", include_tools_spec=True))

        # alpaca.jsonl: legacy single-turn shape mirrors turn-0, plus markers.
        _append_jsonl(d / ALPACA, _build_alpaca(sample))

    # ---- session.json (config + counts + asked-set) ------------------------
    def save_session(self, session_id: str, meta: dict[str, Any]) -> None:
        d = self.session_dir(session_id)
        # session.json is rewritten atomically each round.
        tmp = d / (SESSION + ".tmp")
        tmp.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
        tmp.replace(d / SESSION)

    def load_session(self, session_id: str) -> dict[str, Any]:
        f = self._dir(session_id) / SESSION
        if not f.exists():
            raise StoreError(f"session {session_id} not found")
        meta = json.loads(f.read_text(encoding="utf-8"))
        # Rebuild asked-set from raw.jsonl if missing/stale.
        if not meta.get("asked"):
            meta["asked"] = [s["question"] for s in self.iter_samples(session_id)]
        return meta

    # ---- listing + pagination ----------------------------------------------
    def list_sessions(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self.root.exists():
            return out
        for d in sorted(self.root.iterdir(), reverse=True):
            f = d / SESSION
            if not f.exists():
                continue
            try:
                meta = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            out.append(meta)
        return out

    def iter_samples(self, session_id: str) -> Iterator[dict[str, Any]]:
        f = self._dir(session_id) / RAW
        if not f.exists():
            return
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def count_samples(self, session_id: str) -> int:
        f = self._dir(session_id) / RAW
        if not f.exists():
            return 0
        with f.open(encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())

    def delete_session(self, session_id: str) -> bool:
        """Remove a session's entire on-disk directory. Returns True if it
        existed. Safe to call on an active session — the caller (registry)
        cancels the live task first so a mid-run _persist can't resurrect it."""
        import shutil

        d = self._dir(session_id)
        if not d.exists():
            return False
        shutil.rmtree(d)
        return True

    def get_samples(self, session_id: str, offset: int, limit: int) -> tuple[int, list[Sample]]:
        # Stream the file: only the requested page is parsed into Samples.
        total = 0
        page: list[Sample] = []
        for row in self.iter_samples(session_id):
            if offset <= total < offset + limit:
                page.append(Sample(**row))
            total += 1
        return total, page

    # ---- export -------------------------------------------------------------
    def export_path(
        self,
        session_id: str,
        fmt: str,
        include_thinking: bool = True,
        thinking_format: str = "separate_field",
        include_tools_spec: bool = True,
    ) -> Path:
        """Build an export file for the given format and return its path.

        thinking_format:
            separate_field - thinking as its own field on the assistant turn
            inline_tags     - wrap thinking in <think>...</think> inside content, drop the field
            strip           - drop thinking entirely
        include_tools_spec: for sharegpt, include the tools declaration on the
            system message (default true). Set false to export pure conversation
            turns without the tool spec.
        """
        d = self._dir(session_id)
        if not d.is_dir():
            raise StoreError(f"session {session_id} not found")
        fmt = fmt.lower()
        if fmt == "raw":
            return d / RAW
        if fmt == "alpaca":
            return d / ALPACA

        # sharegpt, rebuilt to honour the thinking/tools flags.
        tag = f"{thinking_format}_th{int(include_thinking)}_tools{int(include_tools_spec)}"
        out_path = d / f"sharegpt_{tag}.jsonl"
        with out_path.open("w", encoding="utf-8") as f:
            for row in self.iter_samples(session_id):
                sample = Sample(**row)
                f.write(
                    json.dumps(
                        _build_sharegpt(sample, include_thinking, thinking_format, include_tools_spec),
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        return out_path


# --------------------------------------------------------------------------
# Projection helpers
# --------------------------------------------------------------------------
def _raw_obj(sample: Sample) -> dict[str, Any]:
    """The raw.jsonl record. Drops empty/None new fields so a pure single-turn
    sample serializes byte-identically to the legacy shape."""
    obj = sample.model_dump()
    for k in ("conversation_id", "tools", "system_prompt", "turn_scores", "tool_score"):
        if obj.get(k) is None:
            obj.pop(k, None)
    if not obj.get("turns"):
        obj.pop("turns", None)
        if obj.get("n_turns", 1) == 1:
            obj.pop("n_turns", None)
    return obj


def _apply_thinking(content: str, thinking: str, include_thinking: bool, thinking_format: str) -> dict[str, Any]:
    """Build the assistant message body (without role) honouring thinking flags."""
    thinking = thinking if include_thinking else ""
    if thinking and thinking_format == "inline_tags":
        return {"content": f"{_THINK_OPEN}\n{thinking}\n{_THINK_CLOSE}\n\n{content}"}
    if thinking and thinking_format == "separate_field":
        return {"content": content, "thinking": thinking}
    return {"content": content}


def _legacy_assistant(content: str, thinking: str, include_thinking: bool, thinking_format: str) -> dict[str, Any]:
    body = _apply_thinking(content, thinking, include_thinking, thinking_format)
    return {"role": "assistant", **body}


def _export_assistant_trace(m: AssistantTraceMessage, include_thinking: bool, thinking_format: str) -> dict[str, Any]:
    """OpenAI-style assistant message for an agentic trace step.

    - content: null when empty AND tool_calls present (OpenAI convention); else
      the (possibly thinking-wrapped) content.
    - tool_calls: [{id, type:"function", function:{name, arguments: <JSON STRING>}}]
    - thinking: kept as a non-standard field when present + separate_field.
    """
    body = _apply_thinking(m.content, m.thinking, include_thinking, thinking_format)
    out: dict[str, Any] = {"role": "assistant", **body}
    if m.tool_calls:
        # Null content only when the EFFECTIVE content is empty — i.e. no
        # thinking was inlined into it. Checking the original m.content would
        # discard inline_tags thinking on every tool-calling step (m.content
        # is "" while the teacher is calling a tool, but thinking may be set).
        if not out.get("content"):
            out["content"] = None
        out["tool_calls"] = [
            {
                "id": c.id,
                "type": "function",
                "function": {
                    "name": c.name,
                    "arguments": json.dumps(c.arguments, ensure_ascii=False),
                },
            }
            for c in m.tool_calls
        ]
    return out


def _build_sharegpt(
    sample: Sample,
    include_thinking: bool,
    thinking_format: str,
    include_tools_spec: bool,
) -> dict[str, Any]:
    messages: list[dict[str, Any]] = []

    # System + tools message ONLY when tools are configured on the sample.
    if sample.tools is not None:
        sys_msg: dict[str, Any] = {"role": "system", "content": sample.system_prompt or ""}
        if include_tools_spec:
            sys_msg["tools"] = [t.model_dump() for t in sample.tools]
        messages.append(sys_msg)

    if sample.turns:
        for t in sample.turns:
            messages.append({"role": "user", "content": t.question})
            if t.tool_trace:
                for m in t.tool_trace:
                    if isinstance(m, AssistantTraceMessage):
                        messages.append(_export_assistant_trace(m, include_thinking, thinking_format))
                    else:  # ToolTraceMessage
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": m.tool_call_id,
                                "name": m.name,
                                "content": m.content,
                            }
                        )
            else:
                messages.append(_legacy_assistant(t.answer, t.thinking, include_thinking, thinking_format))
    else:
        # Single-turn (byte-identical to legacy).
        messages.append({"role": "user", "content": sample.question})
        messages.append(_legacy_assistant(sample.answer, sample.thinking, include_thinking, thinking_format))

    return {"messages": messages}


def _build_alpaca(sample: Sample) -> dict[str, Any]:
    obj: dict[str, Any] = {
        "instruction": sample.question,
        "output": sample.answer,
        "thinking": sample.thinking,
        "grade": sample.score,
    }
    if sample.turns and len(sample.turns) > 1:
        obj["n_turns"] = len(sample.turns)
    if sample.tool_score is not None or any(getattr(t, "tool_trace", None) for t in sample.turns):
        obj["tool_assisted"] = True
    return obj


def _append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


store = Store()