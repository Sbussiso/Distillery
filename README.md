# Distillery

Distillery helps you build a training dataset by letting two AI models work together.

- A **teacher** model answers questions. This is a model running on your own machine through [Ollama](https://ollama.com), such as `qwen3:8b`.
- A **judge** model writes the questions and grades every answer. This can be a big cloud model like Claude, or another local model if you want everything free and offline.

Answers that score well are saved. Answers that don't are thrown away. You keep going until you have as many good examples as you asked for. You end up with a clean dataset you can use to fine-tune a smaller "student" model so it learns to behave like the teacher.

If the teacher is a "thinking" model, Distillery also saves its reasoning, so the student can learn to reason too.

```
  Judge writes a question ──► Teacher answers ──► Judge grades it (1–10)
           ▲                                               │
           │                          high enough? keep it │
           └──────────── repeat until you have enough ◄────┘
```

## What you can make with it

- **Simple Q&A pairs**: one question, one answer. This is the default.
- **Conversations**: the judge asks follow-up questions, so each example is a back-and-forth chat. See [Conversations and tools](docs/conversations-and-tools.md).
- **Tool-using examples**: the teacher can call tools like a calculator or a search function, and every step is recorded. Use this to train a model to work as an agent. See [Conversations and tools](docs/conversations-and-tools.md).

Your data downloads in the formats most fine-tuning tools expect: ShareGPT, Alpaca, or the full raw records. See [Your dataset](docs/datasets.md).

## What you need

- [uv](https://docs.astral.sh/uv/), which installs and runs the Python side.
- [Node.js](https://nodejs.org) 20 or newer, which builds the web interface. You only need it once, for setup.
- [Ollama](https://ollama.com), which runs the teacher model on your machine.
- *Optional:* an API key for a cloud judge (Anthropic, OpenAI, Groq or OpenRouter). You can skip this and use a local judge instead.

## Get started

**1. Install the app**

```bash
git clone https://github.com/Sbussiso/Distillery.git
cd Distillery
uv sync
```

**2. Build the web interface**

```bash
cd frontend
npm ci
npm run build
cd ..
```

> If you skip this step, the app still starts, but it shows an older, simpler interface instead.

**3. Start Ollama and download a teacher model**

In a separate terminal:

```bash
ollama serve
```

Then download a model to distill. `qwen3:8b` is a good first choice because it's a thinking model:

```bash
ollama pull qwen3:8b
```

**4. Add your API key (optional)**

```bash
cp .env.example .env
```

Open `.env` and fill in the key for the judge you want to use, such as `ANTHROPIC_API_KEY=...`. If you'd rather not use a cloud model, skip this. You can pick a local judge in the app.

**5. Start Distillery**

```bash
uv run distillery
```

Open <http://127.0.0.1:8000> in your browser.

## Your first run

1. **Teacher:** pick the model you downloaded (`qwen3:8b`). If it's missing from the list, click **Refresh models**.
2. **Judge:** pick a judge model.
   - For the best grading, use a strong cloud model like `anthropic/claude-opus-5`. This needs the API key from step 4.
   - For a free, fully local run, use `ollama/llama3.1:8b`. Run `ollama pull llama3.1:8b` first.

   Click **Test judge** to make sure it's working before you start.
3. **Distillation:** type a few topics, such as `python debugging, sorting algorithms`. Leave everything else as it is for now.
4. Click **Start distillation**.

Each question appears in the table as soon as it's graded, marked kept or rejected. Click any row to read the full exchange and the judge's reasoning. When the run finishes, use **Export dataset** to download your data.

You can click **Stop** at any time. Nothing is lost: everything kept so far is already saved, and you can **Resume** later from where you left off.

> **Tip:** start with a small target (10 is the default) to check that the questions and grades look right before you ask for hundreds.

## Learn more

| Guide | What's in it |
| --- | --- |
| [Settings explained](docs/settings.md) | Every option in the app, what it does, and when to change it |
| [Conversations and tools](docs/conversations-and-tools.md) | Multi-turn chats and tool-using (agent) examples |
| [Your dataset](docs/datasets.md) | Where files are saved, the export formats, and stopping and resuming |
| [Troubleshooting](docs/troubleshooting.md) | Fixes for the most common problems |
| [Development](docs/development.md) | How the code is organised, the HTTP API, and running the tests |

## Good to know

- **Your keys stay yours.** API keys are never saved to disk by the app. They're read from `.env`, or from the key box in the app for that session only.
- **It runs on your machine.** By default the app is only reachable from your own computer, and other websites you visit can't use it behind your back.
- **Questions never repeat.** Every question in a session is checked against the ones already asked, even when you stop and resume.
- **It won't burn money in a loop.** If the judge or Ollama keeps failing, for example because of a wrong key or because Ollama isn't running, the session stops after 5 failures in a row instead of retrying forever. Fix the problem, then click **Resume**.
