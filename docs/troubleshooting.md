# Troubleshooting

Find the symptom you're seeing below. Most problems come down to Ollama not running, a judge model name or key being wrong, or settings that are too strict.

> **Where to look first:** the latest error appears in a banner at the top of the run screen, and the stats bar counts errors as they happen. The terminal where you ran `uv run distillery` shows the server's own log.

---

### "Ollama offline", or "Ollama not reachable" when starting

Distillery can't reach Ollama.

- Make sure Ollama is running: `ollama serve` in a terminal (or open the Ollama app).
- If Ollama runs somewhere other than this computer's default address, set `DISTILLERY_OLLAMA_BASE_URL` in your `.env` file (the default is `http://localhost:11434`), then restart Distillery.

### My model isn't in the teacher list

- Download it first: `ollama pull qwen3:8b` (or whichever model you want).
- Click **Refresh models**.
- Check that the pill in the header says **Ollama online**.

### "Test judge" fails

The message says "judge call failed (check model string + API key)". Check these in order:

1. **The model name.** It needs the provider in front: `anthropic/claude-opus-5`, not `claude-opus-5`. See the [LiteLLM provider list](https://docs.litellm.ai/docs/providers) for exact names.
2. **The API key.** Make sure the right key is in `.env` (for example `ANTHROPIC_API_KEY` for `anthropic/...` models), or paste it into the **API key** box. After editing `.env`, restart Distillery.
3. **Reasoning effort.** Some models don't support it. Set it to `none` and test again.
4. **For a local judge** (`ollama/...`), the model has to be downloaded: `ollama pull llama3.1:8b`.

### The app looks old or plain

You're seeing the older backup interface because the new one hasn't been built. Run this once, then restart Distillery:

```bash
cd frontend && npm ci && npm run build
```

### Almost everything is rejected

Answers are scoring below your **Min score**. Click a rejected row to read the judge's explanation; it usually makes the cause obvious. Common fixes:

- Lower **Min score** a little (7 → 6).
- Choose an easier **Difficulty**, or narrower topics that suit your teacher.
- Loosen your **Grading criteria** if you've set strict ones.
- Try a larger teacher model. Small models struggle with hard questions.

### Lots of "grade failed"

The judge replied, but not in the format Distillery needs (a small JSON object with the score). Distillery already retries once with firmer instructions, so a high count means the judge struggles with the format. Use a stronger judge model, or raise its **Reasoning effort**. Small local judges are the usual cause.

### The session stopped with status `errored`

Distillery stops a session by itself when something keeps going wrong, so it doesn't loop forever (or keep spending money on API calls):

- **"no new question after 5 attempts"**: the judge couldn't come up with a new question. Either the judge is failing (wrong key, provider down, rate limit), or every question it suggests has been asked already. If it's the second case, add more topics or some seed questions.
- **"5 rounds in a row failed"**: answering or grading keeps failing. The message includes the last error. Usually Ollama stopped or the teacher model was unloaded.

Fix the cause, then open the session from **Past distillations** and click **Resume**. You'll pick up exactly where you left off.

### "teacher model … does not support tools; continuing without tools"

The teacher you picked can't call tools through Ollama, so the run carries on as a normal (or multi-turn) run. Pick a model that supports tools if you need tool-using examples. Ollama's model library shows which models have the "tools" capability.

### Many conversations are "aborted"

A conversation is aborted when the teacher gives an empty answer, or when the judge can't keep it going before **Min turns** is reached. Try:

- Lowering **Min turns**.
- Using a stronger judge (it writes the follow-up questions).
- Turning on **Keep completed turns on abort**, so the turns that did finish can still be used.

### It's slow

- Raise **Concurrency** to 2–4 if your computer can run several teacher answers at once.
- Choose a smaller teacher, or turn off **Capture teacher thinking** (reasoning makes answers much longer).
- For conversations, lower **Max turns**. For tools, lower **Max tool rounds**.
- A local judge on the same machine competes with the teacher for memory and GPU. A cloud judge avoids that.

### The run went slightly past my target

With **Concurrency** above 1, a few questions may already be in progress when the target is reached. They're allowed to finish, so you can end up with one or two extra examples. That's expected.

### "Address already in use" when starting Distillery

Something else is using port 8000. Set a different one in `.env`, such as `DISTILLERY_PORT=8010`, and open that port in your browser instead.

### A session still shows `running` after a restart

Sessions that were interrupted (because the app was closed or crashed mid-run) show as `stopped` and can be resumed. If you see one stuck as `running`, make sure you're on the latest version of Distillery.
