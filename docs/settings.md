# Settings explained

This page walks through every option on the setup screen, in the order it appears. For each one you'll find what it does, its default, and when you'd want to change it.

If you're just starting out, the defaults are fine. Fill in a teacher, a judge and some topics, then press start.

- [Teacher](#teacher)
- [Judge](#judge)
- [Distillation](#distillation)
- [Multi-turn](#multi-turn)
- [Tools / agents](#tools--agents)
- [Export](#export)
- [Server settings (.env)](#server-settings-env)

---

## Teacher

The teacher is the model you're distilling: the one whose answers become your dataset. It always runs locally through Ollama.

**Model.** Pick from the models Ollama has downloaded. If a model you just pulled isn't listed, click **Refresh models**.

> **Which teacher should I pick?** If you want the dataset to include reasoning, choose a "thinking" model such as `qwen3:8b` or `deepseek-r1`. For tool-using examples, pick a model that supports Ollama's tools feature. Distillery checks this for you when the run starts and tells you if the model can't use tools.

---

## Judge

The judge is the model that writes questions, grades answers, and (in other modes) writes follow-up questions and pretends to be tools. A judge that's smarter than the teacher gives you better questions and fairer grades.

**Model.** Any model name that [LiteLLM](https://docs.litellm.ai/docs/providers) understands, written as `provider/model`. The box suggests a few. Some examples:

| You want | Use | Needs |
| --- | --- | --- |
| The strongest grading | `anthropic/claude-opus-5` | `ANTHROPIC_API_KEY` |
| A cheaper cloud option | `openai/gpt-4o-mini` | `OPENAI_API_KEY` |
| Speed | `groq/llama-3.3-70b-versatile` | `GROQ_API_KEY` |
| Free and offline | `ollama/llama3.1:8b` | Nothing (run `ollama pull llama3.1:8b` first) |

**Reasoning effort.** Default: `medium`. Lets judges that support it think before they grade: `none`, `low`, `medium` or `high`. More effort usually means fairer grades, but it's slower and uses more tokens. Set it to `none` for judges that don't support it.

**API key.** Optional. Leave this empty to use the key in your `.env` file. If you paste a key here, it's used for this session only and never written to disk.

**Test judge.** Sends one tiny request to check that the model name and key work. Do this before every new setup. It's much nicer to find a typo now than after the run starts.

---

## Distillation

These settings decide what gets asked and what gets kept.

**Topics.** Required. A comma-separated list of subjects, such as `python debugging, sorting algorithms, SQL joins`. The judge writes questions about these, and Distillery steers towards whichever topic has the fewest kept examples so far. That keeps your dataset balanced.

**Difficulty.** Default: `any`. Asks the judge for `easy`, `medium` or `hard` questions, or a mix (`any`).

**Target count.** Default: 10. Range: 1–10,000. How many *kept* examples you want. The run ends when it reaches this number. Rejected answers don't count, so a strict minimum score means more questions get asked.

**Min score (1–10).** Default: 7. The judge scores every answer from 1 to 10. Answers scoring at least this much are kept. Everything else is rejected.

- Raise it (8 or 9) for a smaller, higher-quality dataset.
- Lower it (5 or 6) if too much is being rejected and you care more about volume.

**Concurrency.** Default: 1. Range: 1–16. How many questions are worked on at the same time. More is faster, but your machine has to run that many teacher answers at once, and cloud judges may hit rate limits. Try 2–4 if your computer handles it comfortably.

**Capture teacher thinking.** Default: on. Asks the teacher to reason before answering, and saves that reasoning alongside the answer. Turn it off if your teacher isn't a thinking model or you only want final answers.

**Seed questions.** Optional, one per line. Example questions in the style you want. The judge uses them as inspiration, not as a script.

**Teacher system prompt.** Optional. Instructions given to the teacher before every question. If you leave it empty, the teacher is told to be helpful and accurate, and to reason step by step when the problem calls for it.

**Grading criteria.** Optional. Extra rules for the judge, such as `must include a code example` or `answers should be under 200 words`. They're added to the judge's normal grading instructions.

---

## Multi-turn

Turn this on to collect whole conversations instead of single questions. [Conversations and tools](conversations-and-tools.md) explains how it works.

**Enable multi-turn conversations.** Default: off.

**Min turns / Max turns.** Defaults: 2 and 4. Range: 1–20. Every conversation has at least *min* and at most *max* questions. Between those limits, the judge decides when the conversation has reached a natural end.

**Min turn score (veto).** Optional, 1–10. Off by default. Normally a conversation is graded as a whole. With this set, the judge also scores each answer, and the conversation is rejected if *any* single answer scores below this number. Use it when one weak answer should spoil the whole example.

**Feed prior thinking back into history.** Default: on. When the teacher answers turn 3, it sees the earlier turns. This decides whether it also sees its own earlier reasoning, or only its earlier answers.

---

## Tools / agents

Turn this on to let the teacher call tools while it answers. [Conversations and tools](conversations-and-tools.md) explains how it works and how tools are set up.

**Enable tools.** Default: off.

**+ Add preset / + Blank tool.** Add a ready-made tool (a calculator, a search, a user lookup) or define your own.

**Max tool rounds.** Default: 6. Range: 1–20. How many times the teacher may call tools while answering a single question. If it hits the limit, it's asked to give its final answer without any more tools.

**Tool call timeout (s).** Default: 60. Range: 5–600. How long one tool call may take before it's cut off.

**Keep completed turns on abort.** Default: off. Sometimes a conversation can't finish properly, for example when the teacher gives an empty answer. Normally the whole thing is thrown away. With this on, the turns that did finish are graded and can still be kept.

---

## Export

These appear once a session has data. See [Your dataset](datasets.md) for what each format looks like.

**Format.** `sharegpt` (default), `raw` or `alpaca`.

**Thinking** (ShareGPT only). How the teacher's reasoning appears in the file:

- `separate_field`: in its own `thinking` field next to the answer. This is the default.
- `inline_tags`: inside the answer, wrapped in `<think>…</think>`. Use this to train a model that "thinks out loud".
- `strip`: removed completely.

**Include thinking.** Turn off to leave reasoning out entirely.

**Include tools spec.** For tool-using examples, whether the list of available tools is written into each example.

---

## Server settings (.env)

These are set in the `.env` file (copy `.env.example` to start). You only need them if you want to change how the app itself runs.

| Setting | Default | What it does |
| --- | --- | --- |
| `DISTILLERY_OLLAMA_BASE_URL` | `http://localhost:11434` | Where Ollama is running |
| `DISTILLERY_DATASETS_DIR` | `datasets` | Folder where sessions and datasets are saved |
| `DISTILLERY_HOST` | `127.0.0.1` | Address the app listens on. Keep this unless you know you need it reachable from other machines. |
| `DISTILLERY_PORT` | `8000` | Port the app listens on |
| `DISTILLERY_DEFAULT_MAX_TOKENS` | `2048` | Longest answer (in tokens) the teacher and judge may write |
| `DISTILLERY_CORS_ORIGINS` | *(empty)* | Other websites allowed to call the API from a browser, as a JSON list such as `'["http://localhost:3000"]'`. Leave empty unless you're building your own front end. |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, … | *(empty)* | Keys for cloud judges. Only fill in the ones you use. |
