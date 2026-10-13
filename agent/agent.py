"""
THE AGENT (the MCP host).

Same think -> act -> observe loop as Week 7 and 8, with one difference that is the
entire point of this week:

    THERE IS NOT A SINGLE TOOL NAME IN THIS FILE.

The tool list is whatever the servers reported in their tools/list reply, handed
to this loop as a `toolbox`. Connect a new server in config/mcp_servers.json and
its tools appear in the prompt and become callable, with this file untouched.
That claim is proved by a git diff, not by me saying so.

WHERE THE MODEL RUNS: here, in the host. Every call_json() below is a model call
on our machine. The MCP servers never call a model; they just answer questions
about recipes and ingredients. If the model lived in the server, whoever
connected to it would be paying for someone else's model choice without knowing.

Safe stopping is unchanged from Week 8: limits on steps, time, cost, repeated
calls and unreadable replies.
"""

import json
import time
from dataclasses import dataclass, field

from .llm import LLMError, call_json


@dataclass
class Budget:
    max_steps: int = 8
    max_seconds: float = 600.0
    max_cost_usd: float = 0.01
    max_repeats: int = 2
    max_bad_replies: int = 2


@dataclass
class AgentRun:
    task: str
    status: str = "running"
    answer: str = ""
    steps: list = field(default_factory=list)
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    seconds: float = 0.0


SYSTEM_TEMPLATE = """You are a kitchen assistant that works in steps. These tools are available to you:

{tools}

On every turn reply with exactly ONE JSON object:
  {{"thought": "<one short sentence: what you know and what you need next>",
    "action": "<a tool name from the list above, or final_answer>",
    "args": {{<the tool's arguments>}}}}
To finish: {{"thought": "...", "action": "final_answer", "args": {{"answer": "<your answer>"}}}}

Rules:
- Use only the tools listed above, with exactly the argument names shown.
- Every fact in your answer must come from a tool result. Never guess numbers.
- If a tool returns an error, read it: it usually says what to do differently. Fix your
  call and try once more rather than giving up or making something up.
- Never repeat a tool call you already made; the result is in the steps above.
- Keep the final answer short, and name the recipe or ingredient it came from."""


def _messages(task, steps, tools_text):
    messages = [{"role": "system", "content": SYSTEM_TEMPLATE.format(tools=tools_text)},
                {"role": "user", "content": f"USER TASK: {task}"}]
    for step in steps:
        messages.append({"role": "assistant", "content": json.dumps(
            {"thought": step["thought"], "action": step["action"], "args": step["args"]})})
        observation = step["observation"]
        if len(observation) > 900:
            observation = observation[:900] + " …[truncated]"
        messages.append({"role": "user", "content":
                         f"Result of {step['action']}: {observation}\n"
                         "If this answers the task, reply with final_answer. Otherwise take the next step."})
    return messages


def run_agent(task, toolbox, budget=None, verbose=False, log=print):
    """
    task     what the user asked
    toolbox  anything with .descriptions() and .call(name, args) — in this project an
             MCPToolbox, but the loop neither knows nor cares where the tools came from
    """
    budget = budget or Budget()
    run = AgentRun(task=task)
    started = time.perf_counter()
    tools_text = toolbox.descriptions()
    seen, bad_replies = {}, 0

    while True:
        elapsed = time.perf_counter() - started
        if len(run.steps) >= budget.max_steps:
            run.status = f"stopped: step limit ({budget.max_steps}) reached"
        elif elapsed >= budget.max_seconds:
            run.status = f"stopped: time limit ({budget.max_seconds:.0f}s) reached"
        elif run.cost_usd >= budget.max_cost_usd:
            run.status = f"stopped: cost limit (${budget.max_cost_usd}) reached"
        if run.status != "running":
            break

        try:
            decision, raw, usage = call_json(_messages(task, run.steps, tools_text))
        except LLMError as error:
            run.status = f"error: {error}"
            break
        run.llm_calls += 1
        run.input_tokens += usage["input_tokens"]
        run.output_tokens += usage["output_tokens"]
        run.cost_usd += usage["cost_usd"]

        if not decision or "action" not in decision:
            bad_replies += 1
            if bad_replies >= budget.max_bad_replies:
                run.status = "stopped: model replies were not valid JSON"
                break
            run.steps.append({"n": len(run.steps) + 1, "thought": "(unreadable reply)", "action": "none",
                              "args": {}, "observation": "That was not valid JSON. Reply with the JSON object only.",
                              "server": "-", "seconds": usage["seconds"]})
            continue
        bad_replies = 0
        thought = str(decision.get("thought", ""))
        action = str(decision.get("action", ""))
        args = decision.get("args") or {}

        if action == "final_answer":
            run.answer = str(args.get("answer", "")) if isinstance(args, dict) else str(args)
            run.status = "finished"
            run.steps.append({"n": len(run.steps) + 1, "thought": thought, "action": "final_answer",
                              "args": {}, "observation": "", "server": "-", "seconds": usage["seconds"]})
            if verbose:
                log(f"  step {len(run.steps)}  THINK  {thought}\n           FINAL  {run.answer}")
            break

        key = action + json.dumps(args, sort_keys=True)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > budget.max_repeats:
            run.status = f"stopped: repeated the same tool call ({action}) {seen[key]} times"
            break

        result = toolbox.call(action, args)
        observation = json.dumps(result, ensure_ascii=False)
        run.steps.append({"n": len(run.steps) + 1, "thought": thought, "action": action, "args": args,
                          "observation": observation, "server": toolbox.which_server(action),
                          "seconds": usage["seconds"]})
        if verbose:
            log(f"  step {len(run.steps)}  THINK  {thought}"
                f"\n           ACT    {action}({json.dumps(args)})   [server: {toolbox.which_server(action)}]"
                f"\n           SEE    {observation[:200]}{'…' if len(observation) > 200 else ''}")

    run.seconds = time.perf_counter() - started
    if run.status != "finished" and not run.answer:
        run.answer = f"I couldn't finish this task ({run.status})."
    return run
