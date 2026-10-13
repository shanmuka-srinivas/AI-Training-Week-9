"""
The MCP CLIENT side: connect to whatever servers the config lists, ask each one
what it can do, and offer those tools to the agent.

THE THREE ROLES, in our project:

    HOST    our agent process. It runs the model and decides what to call.
    CLIENT  this file. One connection per server, speaking MCP.
    SERVER  mcp_servers/*.py, and anyone else's server we add to the config.

Nothing here knows the name of a single tool. The tool list comes from the
server's own tools/list reply at start-up, which is what makes adding a second
server a config change rather than a code change.

MCP is asynchronous and our agent loop is plain synchronous Python, so the
connections live on a background thread with their own event loop, and this
class is the ordinary blocking front door to them.
"""

import asyncio
import json
import threading
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config" / "mcp_servers.json"


class MCPToolbox:
    """Every tool discovered from every configured server."""

    def __init__(self, config_path=DEFAULT_CONFIG):
        self.config_path = Path(config_path)
        self.servers = json.loads(self.config_path.read_text(encoding="utf-8"))["mcpServers"]
        self.tools = {}          # tool name -> {"server", "description", "schema"}
        self.server_info = {}    # server name -> {"version", "tool_names"}
        self.call_log = []
        self._loop = None
        self._thread = None
        self._ready = threading.Event()
        self._stop = None

    # ---- lifecycle ---------------------------------------------------------

    def __enter__(self):
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait()
        if self._error:
            raise self._error
        return self

    def __exit__(self, *exc):
        if self._loop:
            self._loop.call_soon_threadsafe(self._stop.set)
        if self._thread:
            self._thread.join(timeout=20)

    _error = None

    def _run_loop(self):
        asyncio.run(self._main())

    async def _main(self):
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        self._sessions = {}
        try:
            async with self._connect_all():
                self._ready.set()
                await self._stop.wait()
        except Exception as error:   # surfaced on the calling thread
            self._error = error
            self._ready.set()

    def _connect_all(self):
        """Open every configured server and keep them all open together."""
        from contextlib import AsyncExitStack, asynccontextmanager

        @asynccontextmanager
        async def opened():
            async with AsyncExitStack() as stack:
                for name, spec in self.servers.items():
                    params = StdioServerParameters(
                        command=spec["command"], args=spec.get("args", []), env=spec.get("env"),
                    )
                    read, write = await stack.enter_async_context(stdio_client(params))
                    session = await stack.enter_async_context(ClientSession(read, write))
                    initialised = await session.initialize()

                    listing = await session.list_tools()          # <- DISCOVERY
                    self._sessions[name] = session
                    self.server_info[name] = {
                        "server_name": initialised.server_info.name,
                        "version": initialised.server_info.version,
                        "protocol": initialised.protocol_version,
                        "tool_names": [t.name for t in listing.tools],
                    }
                    for tool in listing.tools:
                        key = tool.name if tool.name not in self.tools else f"{name}.{tool.name}"
                        self.tools[key] = {
                            "server": name,
                            "real_name": tool.name,
                            "description": (tool.description or "").strip(),
                            "schema": tool.input_schema or {},
                        }
                yield

        return opened()

    # ---- what the agent uses ----------------------------------------------

    def descriptions(self):
        """The tool list, written out for the model, straight from tools/list."""
        blocks = []
        for name, tool in self.tools.items():
            schema = tool["schema"].get("properties", {}) or {}
            required = set(tool["schema"].get("required", []) or [])
            args = ", ".join(
                f"{arg}: {spec.get('type', 'any')}" + ("" if arg in required else " (optional)")
                for arg, spec in schema.items()
            )
            blocks.append(f"{name}({args})\n    {tool['description']}")
        return "\n\n".join(blocks)

    def call(self, name, args):
        """Run a discovered tool and hand back plain data."""
        tool = self.tools.get(name)
        if tool is None:
            return {"error": f"Unknown tool '{name}'. Available: {', '.join(self.tools)}."}
        future = asyncio.run_coroutine_threadsafe(self._call(tool, args or {}), self._loop)
        result = future.result(timeout=60)
        self.call_log.append({"tool": name, "server": tool["server"], "args": args})
        return result

    async def _call(self, tool, args):
        session = self._sessions[tool["server"]]
        try:
            result = await session.call_tool(tool["real_name"], dict(args))
        except Exception as error:
            # A broken call must come back as data the model can read and retry from,
            # never as a crash that ends the run.
            return {"error": f"the tool call failed: {error}"}
        if getattr(result, "structured_content", None):
            inner = result.structured_content
            return inner.get("result", inner) if isinstance(inner, dict) else inner
        texts = [c.text for c in result.content if getattr(c, "type", "") == "text"]
        joined = "\n".join(texts)
        try:
            return json.loads(joined)
        except (json.JSONDecodeError, TypeError):
            return {"text": joined}

    def which_server(self, tool_name):
        tool = self.tools.get(tool_name)
        return tool["server"] if tool else "unknown"
