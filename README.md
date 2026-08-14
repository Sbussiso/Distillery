# Distillery

A local app for distilling a **teacher** LLM into a fine-tuning dataset. The
teacher is always a local **Ollama** model (the thing being distilled). A
pluggable **judge** — any provider via [LiteLLM](https://docs.litellm.ai/), so
you can point Claude or any bigger model at the small local one — generates
questions from your topics, the teacher answers, and the judge grades the
answer. Answers that pass the grade threshold are kept as dataset samples.
Thinking models' reasoning is captured, so the dataset can train a student to
reason too.

```
judge writes a question  ──>  teacher answers (think:true)  ──>  judge grades
        └── keep if score >= threshold ──>  append to dataset (with thinking)
        rinse & repeat until target_count kept samples
```

## Output

Per session, under `datasets/<session_id>/`:

- `sharegpt.jsonl` — `{"messages":[{user},{assistant, thinking}]}` (default fine-tuning format)
- `raw.jsonl` — full records: question, answer, thinking, score, judge reasoning, models, timestamp
- `alpaca.jsonl` — `{instruction, output, thinking, grade}`
- `session.json` — config + counts + asked-set (enables resume after stop/crash)

Exports support a `thinking_format` toggle: `separate_field` (default),
`inline_tags` (wraps reasoning as `…\n{thinking}\n\n{answer}` in the assistant
content, for training a student to emit think tags), or `strip`.

## Setup

Requirements: [uv](https://docs.astral.sh/uv/) and [Ollama](https://ollama.com)
installed.

```bash
uv sync                          # install deps
cp .env.example .env             # then add provider API keys if using a cloud judge
ollama serve                     # in another terminal
ollama pull qwen3:8b             # a thinking teacher
```

## Run

```bash
uv run python -m distillery      # or: uv run distillery
```

Open <http://127.0.0.1:8000>.

## Usage

1. **Teacher** — pick the Ollama model to distil (e.g. `qwen3:8b`).
2. **Judge** — choose any LiteLLM model string. For a fully-local, no-cost run
   use `ollama/llama3.1:8b` (no API key). For stronger grading use
   `anthropic/claude-opus-5` (set `ANTHROPIC_API_KEY` in `.env`). Hit **Test
   judge** to confirm.
3. **Distillation** — give topics, optional seed questions, target count, min
   score (1-10), difficulty, concurrency, and the capture-thinking toggle.
4. **Start** — watch rounds stream in over the WebSocket. Stop anytime; the
   partial dataset is on disk and exportable.
5. **Export** — download ShareGPT / raw / Alpaca with the thinking-format you
   want, anytime.
6. **Past sessions** — resume a stopped/errored session from where it left off
   (no duplicate questions).

## Concurrency

The question generator is a single serialized producer (so questions never
duplicate); `concurrency` controls how many answer+grade workers run in
parallel. Default `1` is the simple sequential model; raise it for throughput.

## Notes

- The teacher uses a direct Ollama client (`/api/chat` with `think: true`) so
  reasoning is reliably captured in `message.thinking`. LiteLLM does not
  officially expose Ollama reasoning, which is why the judge uses LiteLLM but
  the teacher does not.
- Per-round errors (Ollama down, judge non-JSON, bad key) are non-fatal: they
  increment an error/grade-failed counter and the run continues.
- API keys are never persisted by the app; LiteLLM reads them from env, or you
  pass one per-request from the UI.