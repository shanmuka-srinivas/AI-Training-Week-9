"""
Capture the raw MCP conversation, by hand, with no SDK in the way.

    python capture_wire.py

This starts the ingredient-database server as a subprocess and talks to it over
stdin/stdout in raw JSON-RPC: initialize -> initialized -> tools/list ->
tools/call. Every message sent and received is written to results/wire.json,
with a hand-written note on each top-level field.

The point is to see that MCP is not magic: it is JSON lines over a pipe.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERVER = [sys.executable, str(ROOT / "mcp_servers" / "ingredient_server.py")]
PROTOCOL = "2025-11-25"

ANNOTATIONS = {
    "jsonrpc": "Always \"2.0\". MCP is JSON-RPC 2.0, an old and boring standard, which is the point.",
    "id": "Matches a reply to its request. Notifications have no id because nothing answers them.",
    "method": "What is being asked for: initialize, tools/list, tools/call.",
    "params": "The arguments for that method.",
    "result": "The server's answer. A reply has either result or error, never both.",
    "error": "A protocol-level failure (bad method, bad arguments). A TOOL that fails normally still "
             "returns result, with isError set, so the model can read it and recover.",
    "protocolVersion": "Which version of MCP both sides agree to speak.",
    "capabilities": "What each side supports: tools, resources, prompts, sampling.",
    "serverInfo": "The server's own name and version, as it reports itself.",
    "clientInfo": "Our name and version, as the host reports itself.",
    "tools": "The discovered tool list. THIS is what makes a tool usable without writing any code: "
             "name, description and a JSON Schema for the arguments.",
    "inputSchema": "JSON Schema for the tool's arguments. The host shows this to the model so it knows "
                   "what to pass.",
    "content": "The tool's output, as a list of content blocks (usually one text block).",
    "structuredContent": "The same output as typed JSON, when the tool declares an output schema.",
    "isError": "Set when the tool itself failed although the protocol worked. In our capture the "
               "failing call shows isError=false, because the tool chose to RETURN a description of "
               "the problem as ordinary data (\"'unicorn tears' is not in the ingredient database\", "
               "plus did_you_mean and next_step) instead of raising. That is the recoverable pattern: "
               "the model reads it and fixes its own call. An exception would have become a "
               "JSON-RPC error and ended the step.",
    "instructions": "A short note from the server about what it is for. The host may show it to the model.",
}


class Wire:
    """A raw JSON-RPC conversation over the server's stdin/stdout."""

    def __init__(self, command):
        self.process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1,
        )
        self.log = []
        self._id = 0

    def send(self, method, params=None, notification=False):
        message = {"jsonrpc": "2.0", "method": method}
        if not notification:
            self._id += 1
            message["id"] = self._id
        if params is not None:
            message["params"] = params
        line = json.dumps(message)
        self.log.append({"direction": "host -> server", "raw": line, "parsed": message})
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()
        if notification:
            return None
        return self.receive()

    def receive(self):
        while True:
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError("the server closed the pipe")
            line = line.strip()
            if not line:
                continue
            message = json.loads(line)
            self.log.append({"direction": "server -> host", "raw": line, "parsed": message})
            if "id" in message:        # skip any notifications the server sends first
                return message

    def close(self):
        self.process.stdin.close()
        self.process.terminate()


def main():
    wire = Wire(SERVER)
    try:
        wire.send("initialize", {
            "protocolVersion": PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "recipe-agent-host", "version": "1.0.0"},
        })
        wire.send("notifications/initialized", {}, notification=True)
        wire.send("tools/list", {})
        wire.send("tools/call", {"name": "grams_to_cups",
                                 "arguments": {"name": "strong white bread flour", "grams": 900}})
        # One deliberately failing call, to show what a RECOVERABLE tool error looks like
        # on the wire: result, not error.
        wire.send("tools/call", {"name": "grams_to_cups",
                                 "arguments": {"name": "unicorn tears", "grams": 100}})
    finally:
        wire.close()

    fields = sorted({k for entry in wire.log for k in entry["parsed"]} |
                    {k for entry in wire.log for k in (entry["parsed"].get("result") or {})
                     if isinstance(entry["parsed"].get("result"), dict)})
    out = {
        "what_this_is": "The raw MCP conversation with the ingredient-database server, captured "
                        "without the SDK: plain JSON-RPC lines over stdin/stdout.",
        "where_the_model_runs": "Nowhere in this file. Every line below is the host asking the server "
                                "for data and the server answering. The model is called only by the "
                                "host (agent/agent.py) to decide WHICH of these calls to make; the "
                                "server never calls a model and does not know one exists.",
        "transport": "stdio: the server is a child process; requests go to its stdin, replies come "
                     "back on its stdout, one JSON object per line.",
        "field_notes": {field: ANNOTATIONS.get(field, "(no note)") for field in fields},
        "exchange": wire.log,
    }
    path = ROOT / "results" / "wire.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"captured {len(wire.log)} messages -> {path}\n")
    for entry in wire.log:
        parsed = entry["parsed"]
        label = parsed.get("method") or ("result" if "result" in parsed else "error")
        print(f"  {entry['direction']:<16} {label:<28} {entry['raw'][:96]}")


if __name__ == "__main__":
    main()
