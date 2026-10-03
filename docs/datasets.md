# Your dataset

This page covers where your data is saved, what the export formats look like, and how stopping, resuming and deleting work.

## Where it's saved

Every run is a **session** with its own short ID (like `3f9a1c2b7e4d`). Everything for that session lives in one folder:

```
datasets/
└── 3f9a1c2b7e4d/
    ├── raw.jsonl        ← every kept example, with all details (the master copy)
    ├── sharegpt.jsonl   ← the same examples in ShareGPT format
    ├── alpaca.jsonl     ← the same examples in Alpaca format
    └── session.json     ← the session's settings, counts and progress
```

Each kept example is written to disk the moment it's accepted. If the app crashes or you close it, you lose at most the questions that were still being worked on.

The `.jsonl` files have **one example per line**, which is what most fine-tuning tools expect.

> You can change where sessions are saved with `DISTILLERY_DATASETS_DIR` in your `.env` file.

## Downloading (export)

The easiest way to get your data is the **Export dataset** panel in the app. It builds a fresh file with the options you choose, and you can do this any time, even while a run is still going.

### ShareGPT (recommended)

A list of chat messages per example. Most fine-tuning tools (Axolotl, LLaMA-Factory, Unsloth and others) accept it, and it's the only format that holds whole conversations and tool calls.

```json
{"messages": [
  {"role": "user", "content": "Why is the sky blue?"},
  {"role": "assistant",
   "content": "Because air scatters blue light more than red light (Rayleigh scattering).",
   "thinking": "Short wavelengths scatter more..."}
]}
```

*(Spread over several lines here for readability. In the file, each example is one line.)*

#### Choosing how reasoning appears

If your teacher is a thinking model, choose where its reasoning goes with the **Thinking** option:

**`separate_field`** (default) puts the reasoning in its own `thinking` field, as shown above.

**`inline_tags`** puts the reasoning inside the answer, wrapped in think tags. Use this if you want the student to learn to "think out loud" before answering:

```json
{"role": "assistant", "content": "<think>\nShort wavelengths scatter more...\n</think>\n\nBecause air scatters blue light more than red light (Rayleigh scattering)."}
```

**`strip`** removes the reasoning and keeps only the final answer:

```json
{"role": "assistant", "content": "Because air scatters blue light more than red light (Rayleigh scattering)."}
```

#### Conversations

A multi-turn example is simply a longer list of messages, alternating between `user` and `assistant`:

```json
{"messages": [
  {"role": "user", "content": "What's a Python list comprehension?"},
  {"role": "assistant", "content": "..."},
  {"role": "user", "content": "How is that different from a generator expression?"},
  {"role": "assistant", "content": "..."}
]}
```

#### Tool-using examples

These start with a `system` message listing the tools the model may use. Then come the tool calls, each tool's result (as a `tool` message), and the final answer:

```json
{"messages": [
  {"role": "system", "content": "You are a helpful assistant.",
   "tools": [{"type": "function", "function": {"name": "calculator", "description": "Evaluate arithmetic.", "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}}}}]},
  {"role": "user", "content": "What is 17*23?"},
  {"role": "assistant", "content": null,
   "tool_calls": [{"id": "call_0", "type": "function", "function": {"name": "calculator", "arguments": "{\"expression\": \"17*23\"}"}}]},
  {"role": "tool", "tool_call_id": "call_0", "name": "calculator", "content": "391"},
  {"role": "assistant", "content": "17 × 23 = 391."}
]}
```

This follows the OpenAI tool-calling format. Untick **Include tools spec** if you don't want the tool list in the system message.

### Alpaca

A simple instruction → output pair per example, popular with older fine-tuning scripts:

```json
{"instruction": "Why is the sky blue?", "output": "Because air scatters blue light more than red light (Rayleigh scattering).", "thinking": "Short wavelengths scatter more...", "grade": 9}
```

> **Heads-up:** Alpaca can only hold one question and one answer. For conversations, it keeps just the first exchange (and adds `"n_turns"` so you can tell). For tool-using examples it keeps only the final answer (and adds `"tool_assisted": true`). Use ShareGPT for those.

### Raw

The complete record of each example, including the grade, the judge's explanation, which models were used, and when. Use this for your own analysis, or to convert to a format not listed here.

```json
{"question": "Why is the sky blue?",
 "answer": "Because air scatters blue light more than red light (Rayleigh scattering).",
 "thinking": "Short wavelengths scatter more...",
 "score": 9, "passed": true,
 "judge_reasoning": "Accurate and concise.",
 "teacher_model": "qwen3:8b", "judge_model": "anthropic/claude-opus-5",
 "topics": ["physics"], "difficulty": "easy",
 "timestamp": "2026-10-03T12:00:00+00:00"}
```

Conversations and tool-using examples also carry `turns` (every question, answer and tool step), `conversation_id`, and, when the judge provided them, `turn_scores` and `tool_score`.

---

## Stopping, resuming and deleting

### Stopping

Click **Stop** at any time. Questions that are already being answered are finished and graded. Questions still waiting in line are skipped. Everything kept so far stays on disk, ready to export.

### Session statuses

Every session in **Past distillations** shows one of these:

| Status | Meaning |
| --- | --- |
| `running` | Still working |
| `completed` | Reached the target count |
| `stopped` | You stopped it (or the server was shut down) |
| `errored` | Something kept failing, so it stopped itself. See [Troubleshooting](troubleshooting.md). |

### Resuming

Open a stopped or errored session from **Past distillations** and click **Resume**. It carries on with the same settings, the same counts, and the same list of questions already asked, so you won't get duplicates.

If you typed the judge API key into the app instead of putting it in `.env`, the key is reused when you resume, but only while the app keeps running. After a restart, put the key in `.env` (keys are never saved to disk).

### Deleting

Click the bin icon next to a session to delete it. This **permanently removes its folder and all its data**, so export anything you want to keep first. Deleting a running session stops it first.
