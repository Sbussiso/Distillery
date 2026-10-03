# Conversations and tools

By default, every example in your dataset is a single question and a single answer. Distillery can also collect two richer kinds of example:

- **Conversations**, where the judge keeps asking follow-up questions, so each example is a whole back-and-forth chat.
- **Tool-using examples**, where the teacher can call tools (like a calculator) while working out its answer, and every step is recorded.

You can use either one on its own, or both together for multi-turn conversations where the teacher uses tools along the way.

---

## Conversations (multi-turn)

### Why you'd want this

A model trained only on single questions often struggles when the conversation continues. It forgets context or contradicts itself. Training on real conversations teaches the student to build on what was already said.

### How it works

1. The judge asks an opening question, and the teacher answers.
2. The judge reads the conversation so far and asks **one follow-up question**. It might dig deeper, check consistency, try an edge case, or move to a related sub-topic.
3. The teacher answers, seeing the full conversation history.
4. This repeats until the conversation reaches **max turns**, or the judge decides it has come to a natural end (it can only do that once **min turns** is reached).
5. The judge grades the **whole conversation** with one score, and it's kept or rejected like any other example.

### Turning it on

In the **Multi-turn** panel, tick **Enable multi-turn conversations** and set:

- **Min turns / Max turns:** how short or long conversations may be. The defaults (2 to 4) are a good start.
- **Min turn score (veto):** optional. Set it if one bad answer should sink the whole conversation, even when the overall grade is fine.
- **Feed prior thinking back into history:** whether the teacher can see its own earlier reasoning. Leave it on unless the history gets too long for your model.

### When a conversation is cut short

Sometimes a conversation can't continue properly. The teacher may give an empty answer, or the judge may stop asking questions or keep repeating itself before **min turns** is reached. Distillery gives the judge one more, firmer try. If that fails too, the conversation is **aborted**. You'll see it counted under "aborted" in the stats.

Aborted conversations are thrown away, unless you turn on **Keep completed turns on abort** (in the Tools panel). Then the turns that did finish are graded and can still be kept.

---

## Tools (agentic examples)

### Why you'd want this

Agents work by calling tools: searching, calculating, looking things up. To train a small model to do that, you need examples showing *when* to call a tool, *what* to send it, and how to *use the result*. Distillery records every one of those steps.

### How it works

For each question:

1. The teacher sees the question and a list of tools it may use.
2. If it decides to call a tool, Distillery runs the tool (see below) and hands the result back.
3. The teacher can keep calling tools, up to **max tool rounds** times, until it gives a final answer. If it hits the limit, it's asked to answer without any more tools.
4. The judge grades the result. When tools were actually used, the judge also looks at whether they were used sensibly.

The saved example contains the whole sequence: each tool call, each result, and the final answer.

### Turning it on

In the **Tools / agents** panel, tick **Enable tools** and add some tools. Your teacher model has to support tools. Distillery checks this at the start of the run, and if the model can't use tools, it tells you and continues without them.

### Adding tools

Click **+ Add preset** for a ready-made tool:

| Preset | What it does | How it runs |
| --- | --- | --- |
| `calculator` | Works out arithmetic like `2+2*3` or `(1+2)**3` | **For real**, using a safe built-in calculator |
| `search` | Searches a pretend knowledge base | **Simulated** by the judge |
| `lookup_user` | Looks up a pretend user profile | **Simulated** by the judge |

Or click **+ Blank tool** to make your own. A tool needs:

- **A name** made of letters, digits and underscores, such as `get_weather`.
- **A description** telling the teacher what it's for. Write this carefully: it's all the teacher has to go on.
- **Parameters**: a JSON schema describing the inputs. For example:

  ```json
  {
    "type": "object",
    "properties": {
      "city": { "type": "string", "description": "City name, e.g. Paris" }
    },
    "required": ["city"]
  }
  ```

### How tools are run

Each tool has a **policy** that decides what happens when the teacher calls it:

- **Simulate** (the default): the judge makes up a realistic result. For example, it invents a plausible weather report for Paris. Nothing real is run, so this is always safe, and it means you can create examples for tools that don't exist yet. To preview what the judge would return, fill in some example arguments on the tool's card and click **test simulate**.
- **Builtin**: the call is run for real by a safe, built-in function. Right now that's only the `calculator`, which can only do arithmetic. It can't run code, open files or reach the network. Each call runs in a separate process and is stopped if it takes longer than the **tool call timeout**. A builtin tool with any other name is simulated instead.
- **Off**: the tool is hidden from the teacher. Use this to switch a tool off without deleting it.

### What gets saved

Tool-using examples are exported in the standard OpenAI-style format: the list of tools, the assistant's tool calls, each tool's result, and the final answer. [Your dataset](datasets.md#tool-using-examples) shows a full example.
