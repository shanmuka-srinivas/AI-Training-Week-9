"""
What does the agent actually discover?

    python list_tools.py

Connects to every server in config/mcp_servers.json, runs the MCP handshake and
tools/list, and prints what came back. The numbers in the write-up come from
here, not from counting by hand.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent.mcp_client import MCPToolbox  # noqa: E402

CONFIG = (Path(sys.argv[sys.argv.index('--config') + 1]) if '--config' in sys.argv
          else Path(__file__).resolve().parent / 'config' / 'mcp_servers.json')


with MCPToolbox(CONFIG) as toolbox:
    print(f"servers in config: {len(toolbox.servers)}")
    for name, info in toolbox.server_info.items():
        print(f"\n  {name}  (reports itself as '{info['server_name']}' v{info['version']}, "
              f"MCP {info['protocol']})")
        for tool_name in info["tool_names"]:
            print(f"      - {tool_name}")
    print(f"\nTOTAL TOOLS DISCOVERED: {len(toolbox.tools)}")
    print("names: " + ", ".join(sorted(toolbox.tools)))
