"""Prompt templates for the judge: question generation and grading.

Kept in one place so the behaviour is editable without touching the judge
client.
"""
from __future__ import annotations

# --------------------------------------------------------------------------
# Question generation
# --------------------------------------------------------------------------
QUESTION_GEN_SYSTEM = """\
You are a question author for an LLM distillation dataset. You write ONE \
high-quality, self-contained question per turn that another model must answer.

Rules:
- The question must be self-contained (no "given the above", no context the \
answering model lacks).
- Ask for a real answerable task, not opinions about models.
- Vary the phrasing, angle, and sub-topic across questions; never repeat or \
lightly rephrase a question from the already-asked list.
- If seeds are provided, vary around their *style and domain*, do not copy \
them.
- Match the requested difficulty.
- Output ONLY the question text. No preamble, no quotes, no numbering, no \
explanation."""


QUESTION_GEN_USER = """\
Topics: {topics}
Difficulty: {difficulty}
Seeds (vary around their style, do not copy):
{seeds}
Already asked (do not repeat or near-rephrase any of these):
{asked}
Coverage so far (kept samples per topic): {topic_counts}
Under-covered topic to favour this round: {steer_topic}

Write ONE new question. Pick a fresh angle on the topics — favour the \
under-covered topic where reasonable. Output ONLY the question text."""


# --------------------------------------------------------------------------
# Grading
# --------------------------------------------------------------------------
GRADING_SYSTEM = """\
You are a strict but fair grader of an answering model's response. You judge \
whether the answer is good enough to keep in a high-quality distillation \
dataset.

Rubric (each 1-10, combine into one overall score):
- Correctness: is the answer factually right?
- Completeness: does it fully address the question?
- Clarity: is it clear and well-structured?

Return ONLY a JSON object, nothing else, in exactly this shape:
{{"score": <integer 1-10>, "passed": <true|false>, "reasoning": "<one or two sentences>"}}

"passed" should be true only when the overall score is high enough that you \
would want a student model trained on this answer. When in doubt, be strict."""


GRADING_USER = """\
Question:
{question}

Answer:
{answer}

{criteria_line}

Grade it now. Return ONLY the JSON object."""


# --------------------------------------------------------------------------
# Multi-turn: follow-up question generation (turns 2..N), called from the
# worker. The judge acts as a curious user probing the teacher.
# --------------------------------------------------------------------------
FOLLOWUP_SYSTEM = """\
You are a curious user holding a conversation with a helpful assistant. Your \
job is to ask ONE probing follow-up question that deepens or broadens the \
conversation.

Rules:
- Ask exactly ONE self-contained follow-up question. It must make sense given \
the turns so far.
- Vary the angle: probe depth, consistency, an edge case, or a related \
sub-topic. Do NOT merely repeat or lightly rephrase an earlier question.
- Match the difficulty of the conversation so far.
- Output ONLY the question text. No preamble, no quotes, no numbering, no \
explanation.
{can_done_line}"""


FOLLOWUP_USER = """\
Topics: {topics}
Conversation so far ({turn_count} turn(s)):
{transcript}
Turn budget: {min_turns}-{max_turns} (you are about to ask turn {next_turn}).

Write ONE follow-up question. Output ONLY the question text{done_clause}."""


# --------------------------------------------------------------------------
# Multi-turn: whole-conversation grading (one grade per multi-turn sample).
# JSON shape is a superset of single-turn Grade (+ turn_scores).
# Thinking is OMITTED from the grading transcript — judge grades visible answers.
# --------------------------------------------------------------------------
CONVERSATION_GRADING_SYSTEM = """\
You are a strict but fair grader of a multi-turn conversation between a user \
and an assistant. You judge whether the WHOLE conversation is good enough to \
keep in a high-quality distillation dataset.

Rubric (each 1-10, combine into one overall score):
- Correctness: are the assistant's answers factually right across all turns?
- Completeness: does the assistant fully address each question, given the \
prior turns?
- Coherence-of-flow: do the turns build on each other naturally? Is the \
assistant consistent across turns?
- Depth: does the conversation probe meaningfully beyond surface answers?

Return ONLY a JSON object, nothing else, in exactly this shape:
{{"score": <integer 1-10>, "passed": <true|false>, "reasoning": "<one or two sentences>", "turn_scores": [<integer 1-10>, one per assistant turn, in order>]}}

"passed" should be true only when you would want a student model trained on \
this conversation. "turn_scores" must contain exactly one entry per assistant \
turn, in order. When in doubt, be strict."""


CONVERSATION_GRADING_USER = """\
Conversation ({n_turns} turn(s)):
{transcript}

{criteria_line}

Grade the whole conversation now. Return ONLY the JSON object."""


# --------------------------------------------------------------------------
# Tools: tool simulation. The judge/LiteLLM acts AS the tool and returns a
# plausible result string. Used for ALL tools with exec_policy="simulate".
# --------------------------------------------------------------------------
TOOL_SIMULATION_SYSTEM = """\
You are simulating a tool that an AI assistant has called. You are NOT the \
assistant; you ARE the tool. Given the tool's name, description, parameter \
schema, and the specific arguments the assistant passed, return ONLY the \
result string that the real tool would produce — nothing else.

Rules:
- Return ONLY the tool's result as plain text. No preamble, no explanation, \
no quoting, no markdown fences.
- If the arguments violate the parameter schema or are nonsensical, return a \
short string beginning with "[error: ...]" describing the problem.
- Be plausible and internally consistent with the tool's described behavior.
- Never execute real code, never access the network or filesystem. You are \
producing a synthetic result for a distillation dataset.
- Keep the result concise (a few lines at most)."""


TOOL_SIMULATION_USER = """\
Tool name: {tool_name}
Tool description: {tool_description}
Parameter schema (JSON Schema):
{parameters}

Arguments passed by the assistant:
{arguments}

Return ONLY the result string this tool would produce for these arguments."""


# Final-answer nudge injected as a system message when max_tool_rounds is hit.
FINAL_ANSWER_NO_TOOLS = (
    "You have used all of your available tool calls. Provide your final "
    "answer now, without calling any further tools."
)


# --------------------------------------------------------------------------
# Tools: agentic conversation grading. Used ONLY when tools were ACTUALLY used
# (at least one Turn has a non-empty tool_trace). Otherwise the multi-turn
# CONVERSATION_GRADING prompt runs byte-identical.
# --------------------------------------------------------------------------
AGENTIC_GRADING_SYSTEM = """\
You are a strict but fair grader of an AI assistant's multi-turn conversation \
that included tool use. You judge whether the conversation is good enough to \
keep in a high-quality distillation dataset for training an agentic student.

Rubric (each 1-10, combine into ONE overall score):
- Correctness: are the final answers factually right?
- Completeness: do the final answers fully address each question?
- Clarity: are the answers clear and well-structured?

Tool-use dimensions (fold into the overall score):
- Tool selection: did the assistant call the RIGHT tool for each subtask? \
Were calls unnecessary, or was a necessary call missed?
- Tool arguments: were the arguments well-formed and sufficient?
- Result interpretation: did the assistant use the tool results correctly, \
without hallucinating or ignoring them?
- Termination: did it stop calling tools at the right time (not premature, \
not excessive)?

Special rules:
- Do NOT penalize abstaining from tool use when the question does not warrant \
it. DO penalize when a tool was clearly necessary (exact arithmetic, external \
data, a declared tool that would have prevented a wrong answer) and the model \
answered without it.
- Cap the score at 4 (passed=false) if the assistant looped on repeated \
identical calls showing no progress AND this prevented a usable final answer.
- If a tool result body was truncated for length, do not penalize the assistant \
for content you cannot see; a "[result truncated]" or "[dropped]" marker means \
the full result was trimmed.

Return ONLY a JSON object, nothing else, in exactly this shape:
{{"score": <integer 1-10>, "passed": <true|false>, "reasoning": "<one or two sentences>", "tool_score": <integer 1-10 or null>, "turn_scores": [<integer per turn>]}}

"tool_score" is an informational sub-score for tool use (null if no tools were \
used in a turn). "turn_scores" is a per-turn overall score. "passed" should be \
true only when the overall score is high enough that you would want a student \
model trained on this conversation."""


AGENTIC_GRADING_USER = """\
Conversation (tools used: {tools_summary}):

{transcript}

{criteria_line}

Grade it now. Return ONLY the JSON object."""


# --------------------------------------------------------------------------
# Judge connectivity test
# --------------------------------------------------------------------------
TEST_PROMPT = "Reply with exactly: OK"