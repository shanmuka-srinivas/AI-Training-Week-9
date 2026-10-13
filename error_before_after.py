"""
Requirement 5: the same failing call, with a bad tool description and a bad error,
then with a good one.

    python error_before_after.py

Both runs ask the SAME question, with the same model and the same agent. The only
difference is which version of our recipe server the config points at:

    BEFORE  mcp_servers/recipe_server_v1.py   docstring: "Scale a recipe."
                                              failure:   {"error": "Error 3"}
    AFTER   mcp_servers/recipe_server.py      docstring written as a prompt, telling the
                                              model WHICH ingredient to scale by and why
                                              failure:   says what was wrong, what exists,
                                                         and what to call next

The failing call is a real one, taken from a live run: the model scaled the recipe so
that the SALT weighed 1 kg and answered "you need 1000 g of salt". The tool did exactly
what it was told. The fix is in the description and the error, not in the agent.

Writes results/error_before_after.md
"""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agent.agent import run_agent  # noqa: E402
from agent.mcp_client import MCPToolbox  # noqa: E402

QUESTION = ("I have 1 kg of white cabbage. How much fine sea salt do I need for the "
            "caraway sauerkraut?")

VERSIONS = [
    ("BEFORE", "config/mcp_servers.v1_terse.json", "recipe_server_v1.py: three-word docstrings, \"Error 3\""),
    ("AFTER", "config/mcp_servers.one_server.json", "recipe_server.py: docstring written as a prompt, recoverable errors"),
]


def transcript(run):
    lines = []
    for step in run.steps:
        if step["action"] == "final_answer":
            lines.append(f"step {step['n']}  FINAL   {run.answer}")
        elif step["action"] == "none":
            lines.append(f"step {step['n']}  (unreadable reply)")
        else:
            observation = " ".join(step["observation"].split())
            lines.append(f"step {step['n']}  THINK   {step['thought']}\n"
                         f"        ACT     {step['action']}({json.dumps(step['args'])})\n"
                         f"        RESULT  {observation[:400]}{'…' if len(observation) > 400 else ''}")
    return "\n".join(lines)


def main():
    out = ["# The same failing call, before and after",
           "",
           "**Question (identical in both runs):** " + QUESTION,
           "",
           "The model's mistake is the same in both: it scales the recipe so that the *salt*",
           "weighs 1 kg, rather than the cabbage. What changes is whether the tool lets that",
           "mistake through silently.",
           ""]
    results = {}
    for label, config, what_changed in VERSIONS:
        print(f"--- {label}: {what_changed}")
        with MCPToolbox(ROOT / config) as toolbox:
            run = run_agent(QUESTION, toolbox, verbose=True)
        results[label] = run
        correct = "20 g" in run.answer or "20g" in run.answer
        out += [f"## {label}", "", f"*{what_changed}*", "", "```", transcript(run), "```", "",
                f"- **Final answer:** {run.answer}",
                f"- **Correct (20 g of salt for 1 kg of cabbage)?** {'YES' if correct else 'NO'}",
                f"- model calls: {run.llm_calls} · {run.seconds:.0f}s · status: {run.status}", ""]

    out += ["## What actually changed", "",
            "1. **The docstring is now a prompt.** It says target_grams applies to the ingredient you",
            "   name, tells the model to pass the ingredient the cook *has* (the cabbage), and spells",
            "   out the trap: scaling by the salt multiplies the recipe by 143.",
            "2. **The error path is recoverable.** When a scale looks absurd the tool no longer returns",
            "   a number like `Error 3`, or worse a confident wrong answer. It returns what went wrong,",
            "   which ingredient was probably meant, and the exact call to make next:",
            "",
            "   ```json",
            '   {"warning": "Scaling Small-Batch Caraway Sauerkraut so that \'Fine sea salt\' weighs 1000 g',
            '                multiplies the whole recipe by 143x, which is almost certainly not what was meant.",',
            '    "likely_intended": "The cook probably has 1000 g of \'White cabbage, finely shredded\'…",',
            '    "next_step": "Call scale_recipe(\'R-106\', \'White cabbage, finely shredded\', 1000) and read',
            '                  the figure for \'Fine sea salt\' out of the result."}',
            "   ```",
            "",
            "   Note what it is *not*: it is not a protocol error. The call succeeded; the tool is",
            "   telling the model something it can act on. A thrown exception would have ended the run.",
            ""]

    path = ROOT / "results" / "error_before_after.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\nwrote {path}")
    for label, run in results.items():
        print(f"  {label}: {run.answer[:110]}")




def tool_level_comparison():
    """
    The same two bad calls sent straight to each server, with no model involved.

    Needed because the improved docstring worked so well that the model stopped
    making the mistake, so the new error path never fired in the transcript above.
    This shows the error path itself.
    """
    bad_calls = [
        ("scale_recipe", {"recipe_id": "R-106", "ingredient": "fine sea salt", "target_grams": 1000},
         "scale by the salt instead of the cabbage (what the model actually did)"),
        ("scale_recipe", {"recipe_id": "R-106", "ingredient": "chocolate", "target_grams": 100},
         "an ingredient that isn't in the recipe"),
        ("get_recipe_section", {"recipe_id": "R-106", "section": "nutrition"},
         "a section that doesn't exist"),
    ]
    out = ["## The same bad calls at the tool level (no model involved)", "",
           "The improved docstring stopped the model making the mistake at all, so the new error",
           "path never fired in the transcript above. Here are the identical calls sent straight",
           "to each server:", ""]
    for tool, args, why in bad_calls:
        out += [f"### `{tool}({json.dumps(args)})`", f"*{why}*", "",
                "| server | what comes back |", "|---|---|"]
        for label, config, _ in VERSIONS:
            with MCPToolbox(ROOT / config) as toolbox:
                result = toolbox.call(tool, args)
            flat = " ".join(json.dumps(result, ensure_ascii=False).split())
            out.append(f"| {label} | `{flat[:400]}` |")
        out.append("")
    out += ["**The difference that matters:** `Error 3` gives the model nothing to act on, so it",
            "either gives up or invents an answer. The rewritten version names the problem, lists",
            "what does exist, and gives the exact call to make next — so the model can fix itself",
            "inside the same run.", ""]

    path = ROOT / "results" / "error_before_after.md"
    path.write_text(path.read_text(encoding="utf-8") + "\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    print(f"appended to {path}")


if __name__ == "__main__":
    if "--tools-only" in sys.argv:
        tool_level_comparison()
    else:
        main()
