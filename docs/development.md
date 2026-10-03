# Development

This page is for anyone who wants to change Distillery or build on it. It covers how the code is laid out, what happens during a run, the HTTP API, and how to run the tests.

## Project layout

```
src/distillery/
├── __main__.py        Starts the server (uv run distillery)
├── app.py             Creates the FastAPI app and serves the web interface
├── config.py          Settings, read from DISTILLERY_* environment variables / .env
├── routes/api.py      The HTTP and WebSocket API (everything under /api)
├── sessions.py        Keeps track of running sessions and lists past ones
├── distiller.py       The engine: runs a session from first question to last
├── judge.py           Talks to the judge model through LiteLLM
├── ollama.py          Talks to the teacher model through Ollama
├── prompts.py         Every prompt sent to the judge
├── tools_builtin.py   Tools that run for real (currently just the calculator)
├── store.py           Reads and writes the files under datasets/
└── schemas.py         The shapes of requests, responses and saved records

frontend/              The web interface (Svelte 5 + Vite + Tailwind)
static/                An older, simpler interface, served only if frontend/ isn't built
tests/                 Unit tests (pytest)
scripts/               Smoke tests, including ones that need a real Ollama
```

## What happens during a run

When you click **Start distillation**, the server creates a `DistillSession` (in `distiller.py`) and runs it in the background:

- **One producer** asks the judge for new questions and puts them in a queue. There's only ever one, so it can check each new question against everything already asked. That's how duplicates are avoided.
- **Several workers** (as many as the **Concurrency** setting) take questions from the queue. Each worker gets the teacher's answer, runs the tool loop or the follow-up conversation if those are turned on, and then asks the judge for a grade.
- A good result is appended to `raw.jsonl` (and the other formats) straight away. After every round, `session.json` is rewritten, so a session can always be resumed.
- Progress events (question asked, answer given, graded, kept…) are sent over a WebSocket to every open browser tab. Each tab gets its own copy of the events. When a tab connects, it is caught up on conversations already in progress; finished ones are loaded from disk instead.

The run ends when the target count is reached, when you press **Stop**, or when something fails 5 times in a row (in which case the session is marked `errored`).

Why two different clients? The teacher is called through Ollama directly, because that's the reliable way to get a thinking model's reasoning back. The judge goes through LiteLLM, so it can be almost any provider.

## The HTTP API

The web interface uses this API, and you can use it too. Everything lives under `/api`. While the server is running, interactive docs are at <http://127.0.0.1:8000/docs>.

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/api/ollama/health` | Is Ollama reachable? |
| `GET` | `/api/ollama/models` | Models Ollama has downloaded |
| `GET` | `/api/judges/providers` | Suggested judge models |
| `POST` | `/api/judges/test` | Check a judge model and key work |
| `GET` | `/api/tools/presets` | The ready-made tools |
| `POST` | `/api/tools/simulate` | Preview a simulated tool result |
| `POST` | `/api/distill` | Start a session (returns its `session_id`) |
| `GET` | `/api/distill/sessions` | All sessions, running and past |
| `GET` | `/api/distill/{id}` | One session's status and counts |
| `POST` | `/api/distill/{id}/stop` | Stop a session |
| `POST` | `/api/distill/{id}/resume` | Resume a stopped or errored session |
| `DELETE` | `/api/distill/{id}` | Delete a session and its data |
| `GET` | `/api/distill/{id}/samples?offset=0&limit=50` | Kept examples, a page at a time |
| `GET` | `/api/distill/{id}/export?fmt=sharegpt` | Download the dataset. Options: `fmt` (`sharegpt`, `raw`, `alpaca`), `thinking_format` (`separate_field`, `inline_tags`, `strip`), `include_thinking`, `include_tools_spec` |
| `WS` | `/api/distill/{id}/stream` | Live progress events for a running session |

A minimal start request looks like this:

```bash
curl -X POST http://127.0.0.1:8000/api/distill \
  -H 'Content-Type: application/json' \
  -d '{"teacher_model": "qwen3:8b", "judge_model": "ollama/llama3.1:8b", "topics": ["python debugging"], "target_count": 5}'
```

Every field and its limits are listed in `DistillRequest` in `schemas.py`, and in the interactive docs. A few are only available through the API: `max_tokens`, `teacher_timeout` and `judge_timeout`.

## Running the tests

```bash
uv run pytest -q                       # unit tests: no Ollama or API key needed
uv run python scripts/smoke_test.py    # checks export formats and parsing
```

The unit tests replace the teacher and judge with stand-ins, so they're fast and work offline.

There are also two **live** tests that run against a real Ollama. They're fully local and need no API key, but you need these models pulled first:

```bash
ollama pull llama3.2:1b && ollama pull qwen2.5:1.5b-instruct
uv run python scripts/live_multiturn_smoke.py   # a real multi-turn conversation
uv run python scripts/live_agent_smoke.py       # a real tool-calling turn
```

For the web interface:

```bash
cd frontend
npm ci
npm run check    # type-check
npm run build    # production build into frontend/dist
```

CI (`.github/workflows/ci.yml`) runs the unit tests, the smoke test, and the frontend check and build on every pull request and every push to `master`.

## Working on the web interface

Run the backend and the Vite dev server side by side:

```bash
uv run distillery            # terminal 1: the API on port 8000
cd frontend && npm run dev   # terminal 2: the interface on port 5173
```

Open <http://localhost:5173>. Changes reload instantly, and Vite forwards all `/api` requests (including the WebSocket) to the backend. When you're done, `npm run build` updates the copy the backend serves on port 8000.

## Adding a real (builtin) tool

Builtin tools are plain Python functions registered in `tools_builtin.py`. They take the tool call's arguments as a dict and return a string:

```python
@register("word_count")
def word_count(args: dict[str, Any]) -> str:
    text = args.get("text")
    if not isinstance(text, str):
        return "[error: 'text' must be a string]"
    return str(len(text.split()))
```

Any tool with the same name and its policy set to `builtin` will then run this function. Each call runs in a separate process that is killed if it takes longer than the tool call timeout. Even so, a builtin tool must never run arbitrary code or touch files or the network: its arguments are written by a model.
