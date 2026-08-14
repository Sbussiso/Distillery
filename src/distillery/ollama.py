"""Async client for the Ollama teacher model (direct httpx, not LiteLLM).

We go direct because LiteLLM does not officially expose Ollama's separated
`message.thinking` reasoning content, and capturing thinking reliably is a
core requirement of this app. Tool calling is also handled here so that the
full assistant message (content + thinking + tool_calls) is captured in one
place for the trace model.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .config import settings
from .schemas import OllamaModel

# Inline thinking-tag fallback: models that emit reasoning inline even when
# `think:true` wasn't honoured. Handles <think>...</think> tags.
_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str | None = None, timeout: float | None = None) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._timeout = timeout or settings.default_timeout

    async def health(self) -> bool:
        # Ollama has no `GET /api` route (it 404s); `/api/version` is the
        # lightweight Ollama-specific liveness probe (200 + {"version":...}).
        # `GET /` would also work but is any-server, not specifically Ollama.
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get(f"{self.base_url}/api/version")
                return r.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[OllamaModel]:
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            r = await c.get(f"{self.base_url}/api/tags")
            r.raise_for_status()
            data = r.json()
        out: list[OllamaModel] = []
        for m in data.get("models", []):
            details = m.get("details", {}) or {}
            caps = m.get("capabilities", []) or []
            out.append(
                OllamaModel(
                    name=m.get("name", ""),
                    size=m.get("size"),
                    param_size=details.get("parameter_size"),
                    quant=details.get("quantization_level"),
                    capabilities=caps,
                    thinking="thinking" in caps,
                )
            )
        return out

    async def probe_tools(self, model: str) -> bool:
        """One-shot capability probe: does the model accept the `tools` param?

        Sends a trivial request WITH tools and NO self-correction. Returns True
        if the model accepts tools, False if it rejects them (400 mentioning
        tool/capability/support). Used once at session start so we can skip
        sending tools (and avoid a wasted 400->retry per call) when unsupported.
        """
        body = {
            "model": model,
            "messages": [{"role": "user", "content": "hi"}],
            "think": False,
            "stream": False,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "_probe",
                        "description": "capability probe",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as c:
                r = await c.post(f"{self.base_url}/api/chat", json=body)
        except Exception:
            return False
        if r.status_code < 400:
            return True
        lo = r.text.lower()
        return not ("tool" in lo or "capabilit" in lo or "support" in lo)

    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        think: bool = True,
        max_tokens: int | None = None,
        timeout: float | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Chat with the teacher. Returns {'content', 'thinking', 'tool_calls'}.

        - Thinking is taken from `message.thinking` when present (the
          `think:true` separated form). If empty, inline tags are parsed out of
          `content` as a fallback.
        - tool_calls is normalized from Ollama's
          [{'function': {'name', 'arguments': <obj>}}] to
          [{'name', 'arguments': <dict>, 'id': ''}]. Empty list when no tools
          were sent (byte-identical to today).
        - The 'tools' key is OMITTED from the request body when tools is
          None/empty, so plain calls are byte-identical to the no-tools path.
        """
        return await self._chat(
            model, messages, think=think, max_tokens=max_tokens,
            timeout=timeout, tools=tools,
        )

    async def _chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        think: bool,
        max_tokens: int | None,
        timeout: float | None,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "think": think,
            "stream": False,
        }
        if max_tokens is not None:
            body["options"] = {"num_predict": max_tokens}
        # ONLY add 'tools' when non-empty (byte-identical when absent).
        if tools:
            body["tools"] = tools

        async with httpx.AsyncClient(timeout=timeout or self._timeout) as c:
            r = await c.post(f"{self.base_url}/api/chat", json=body)
            if r.status_code >= 400:
                lo = r.text.lower()
                # Self-correct: non-thinking models reject think:true. Retry once
                # without it (carries tools through unchanged).
                if think and "does not support thinking" in lo:
                    return await self._chat(
                        model, messages, think=False, max_tokens=max_tokens,
                        timeout=timeout, tools=tools,
                    )
                # Self-correct: a model lacking tool capability rejects the tools
                # param. Retry once without tools (tool_calls -> []). The session's
                # _tools_active flag is normally flipped by a pre-check, so this is
                # a last-resort per-call recovery.
                if tools and ("tool" in lo or "capabilit" in lo):
                    return await self._chat(
                        model, messages, think=think, max_tokens=max_tokens,
                        timeout=timeout, tools=None,
                    )
                raise OllamaError(f"ollama chat failed ({r.status_code}): {r.text[:500]}")
            data = r.json()

        msg = data.get("message", {}) or {}
        content: str = msg.get("content", "") or ""
        thinking: str = msg.get("thinking", "") or ""

        if not thinking:
            m = _THINK_RE.search(content)
            if m:
                thinking = m.group(1).strip()
                content = _THINK_RE.sub("", content).strip()

        # Parse + normalize tool_calls. Ollama returns arguments as a parsed
        # object; some builds return a string. We normalize to a dict.
        raw_tcs = msg.get("tool_calls", []) or []
        tool_calls: list[dict[str, Any]] = []
        for tc in raw_tcs:
            fn = tc.get("function", {}) or {}
            name = fn.get("name")
            if not name:
                continue  # skip malformed entry
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"raw": args}
            elif not isinstance(args, dict):
                args = {"raw": str(args)}
            tool_calls.append({"name": name, "arguments": args, "id": ""})

        return {"content": content, "thinking": thinking, "tool_calls": tool_calls}


def to_ollama_tools(tool_defs: list) -> list[dict[str, Any]]:
    """Convert a list of ToolDef -> the Ollama tools payload, excluding 'off'."""
    out: list[dict[str, Any]] = []
    for td in tool_defs:
        if getattr(td, "exec_policy", "simulate") == "off":
            continue
        out.append(
            {
                "type": "function",
                "function": {
                    "name": td.name,
                    "description": td.description,
                    "parameters": td.parameters,
                },
            }
        )
    return out


ollama_client = OllamaClient()