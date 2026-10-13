"""
Ask the agent one question and show every step, including WHICH SERVER each tool
call went to.

    python demo_query.py "how much salt for 1 kg of cabbage in the sauerkraut?"
    python demo_query.py --tag two_servers "how many cups is 900 g of bread flour?"

Saves the trace to results/trace_<tag>.json.
"""

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agent.agent import run_agent  # noqa: E402
from agent.mcp_client import MCPToolbox  # noqa: E402

CONFIG = (Path(sys.argv[sys.argv.index('--config') + 1]) if '--config' in sys.argv
          else Path(__file__).resolve().parent / 'config' / 'mcp_servers.json')


parser = argparse.ArgumentParser()
parser.add_argument("question", nargs="+")
parser.add_argument("--tag", default="demo")
parser.add_argument("--config", default=None)
args = parser.parse_args()
question = " ".join(args.question)

with MCPToolbox(CONFIG) as toolbox:
    print(f"Discovered {len(toolbox.tools)} tools from {len(toolbox.servers)} server(s): "
          f"{', '.join(sorted(toolbox.tools))}\n")
    print(f"QUESTION: {question}\n")
    run = run_agent(question, toolbox, verbose=True)
    print(f"\nSTATUS: {run.status} | {run.llm_calls} model calls | {run.seconds:.0f}s")
    print(f"ANSWER: {run.answer}")
    used = [(s["action"], s["server"]) for s in run.steps if s["server"] not in ("-",)]
    print("\nTOOLS USED (tool <- server):")
    for tool, server in used:
        print(f"   {tool}  <-  {server}")

    (ROOT / "results").mkdir(exist_ok=True)
    out = ROOT / "results" / f"trace_{args.tag}.json"
    out.write_text(json.dumps({
        "question": question, "servers_in_config": list(toolbox.servers),
        "tools_discovered": sorted(toolbox.tools),
        "tool_calls": [{"tool": t, "server": s} for t, s in used],
        "status": run.status, "answer": run.answer, "steps": run.steps,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out}")
