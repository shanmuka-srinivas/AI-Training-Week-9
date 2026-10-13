"""
Run the whole week:

    python run_all.py

  1. list the tools discovered with ONE server, then with TWO (config change only)
  2. capture the raw JSON-RPC conversation with the second server
  3. ask the agent a question that can only be answered using the new server
  4. the same failing call with a terse tool description vs a rewritten one
  5. the same bad calls at tool level, with no model involved

Steps 3 and 4 call the local model and take a few minutes; the rest are instant.
Everything runs offline and costs nothing.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STEPS = [
    ("tools discovered with ONE server", ["list_tools.py", "--config", "config/mcp_servers.one_server.json"]),
    ("tools discovered with TWO servers (config change only)", ["list_tools.py"]),
    ("raw JSON-RPC: initialize -> tools/list -> tools/call", ["capture_wire.py"]),
    ("agent query that uses the NEW server", ["demo_query.py", "--tag", "two_servers",
        "I'm scaling the Neapolitan pizza dough to 1500 g of Tipo 00 flour. "
        "How many US cups of flour is that, and does the flour carry any allergen?"]),
    ("docstring + error, before and after (2 model runs)", ["error_before_after.py"]),
    ("the same bad calls at tool level", ["error_before_after.py", "--tools-only"]),
]

for number, (title, command) in enumerate(STEPS, start=1):
    print("=" * 78)
    print(f"STEP {number}/{len(STEPS)}: {title}")
    print("=" * 78)
    if subprocess.run([sys.executable, *command], cwd=ROOT).returncode != 0:
        print(f"STEP {number} failed.")
        raise SystemExit(1)
    print()

print("Done. Read RESULTS.md, then results/.")
print("The zero-diff proof is a git command, not a script:")
print("    git diff HEAD~1 HEAD -- agent/      (empty)")
