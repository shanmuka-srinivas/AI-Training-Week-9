# Recipe Agent: Plugging In Tools the Standard Way (MCP)

*Week 9 · Module 5 (MCP, Multi-agent & A2A) · Track B: Recipes & food*

---

## What is this project for?

Up to Week 8, every tool our recipe agent could use was **wired in by hand**. Searching
recipes, scaling a recipe — all Python functions sitting inside the agent's own code. Two
problems with that:

1. **Nobody else can use our tools.** Another team's AI can't call our recipe scaler,
   because it's just a function buried in our app.
2. **We can't easily use anyone else's.** Adding someone's ingredient database would mean
   editing our agent, testing it, and shipping a new version.

**MCP (Model Context Protocol) fixes this.** It's a standard "socket" between AIs and
tools, like USB for AI apps. A tool that speaks MCP can be plugged into any AI; an AI that
speaks MCP can use any tool.

So this week:

1. We **rebuilt the agent to discover its tools** instead of having them written in. It asks
   each server "what can you do?" when it starts, and uses whatever comes back.
2. We **built our own MCP server** for the recipe cards, which anyone's agent can call.
3. We **bolted on a second server** (an ingredient database, standing in for another team's)
   by editing a config file — **without changing a single line of agent code**, and proved
   that with a git diff.

> **An honest note:** MCP does not make the AI smarter. It's plumbing. The win is reuse and
> easy swapping, not better answers. That's the framing to give a client.

---

## Input

| What goes in | Details |
|---|---|
| **The agent** | The loop from Weeks 7–8, with one change: it has no tool names in it |
| **10 recipe cards** | [data/recipes/](data/recipes/) — read by our own server |
| **An ingredient database** | Weights per cup, allergens and substitutes, inside the second server |
| **A config file** | [config/mcp_servers.json](config/mcp_servers.json) — the only place servers are named |
| **A question** | e.g. *"I'm scaling the pizza dough to 1500 g of flour — how many cups is that, and is there an allergen?"* |

---

## Output

| What comes out | Where |
|---|---|
| **Tools discovered, before and after** | [results/tools_before.txt](results/tools_before.txt), [results/tools_after.txt](results/tools_after.txt) |
| **Proof the agent didn't change** | [results/agent_diff.txt](results/agent_diff.txt) — deliberately empty |
| **The raw MCP conversation**, annotated | [results/wire.json](results/wire.json) |
| **Agent traces** showing which server each tool came from | [results/trace_*.json](results/) |
| **Before/after on a tool description and its error** | [results/error_before_after.md](results/error_before_after.md) |
| **Supply-chain risk note** (5 lines) | [results/risk_note.md](results/risk_note.md) |
| **The write-up** | [RESULTS.md](RESULTS.md) |

### The headline result

| | Before | After |
|---|---|---|
| Servers connected | 1 | 2 |
| **Tools the agent can use** | **3** | **6** |
| **Lines of agent code changed** | — | **0** |
| Lines of config changed | — | 6 |

---

## What happens between input and output

### The three roles (this is the whole idea)

```
   ┌──────────────── HOST: our agent ──────────────────┐
   │  runs the AI model, decides what to call          │
   │                                                   │
   │   CLIENT ──────── MCP ────────► SERVER 1: recipe cards   (ours)
   │   one connection                 search / read / scale
   │   per server                                      │
   │            ──────── MCP ────────► SERVER 2: ingredient db (another team's)
   │                                   cups / allergens / substitutes
   └───────────────────────────────────────────────────┘
```

- **Host** — our app. **The AI model runs here and only here.**
- **Client** — the connection code, one per server ([agent/mcp_client.py](agent/mcp_client.py)).
- **Server** — a separate program offering tools. **No AI inside.** It reads files and does
  arithmetic, and has no idea which AI is calling it.

### Step 1: The agent asks what tools exist

On start-up, the client reads the config, launches each server, and runs the MCP handshake:

```
initialize                 → agree a version, swap names
notifications/initialized  → "ready"
tools/list                 → "here is every tool I have, with its description
                              and the exact arguments it takes"
```

That reply is turned straight into the tool list the model sees. **The agent never knows a
tool name in advance.** Add a server to the config and its tools simply appear.

### Step 2: The agent answers the question

Same think → act → observe loop as before. When it picks a tool, the client sends
`tools/call` to whichever server owns it and hands the result back:

```
step 1  ACT  grams_to_cups({"name": "...flour", "grams": 1500})   [server: ingredient-db]
step 2  ACT  ingredient_info({"name": "...flour"})                [server: ingredient-db]
step 3  FINAL  ...approximately 11.81 US cups, and it carries the allergen gluten.
```

Those two tools did not exist for the agent an hour earlier. No agent code changed.

### Step 3: Proving the agent really didn't change

Easy to claim, so it's proved with git:

```
$ git diff --stat HEAD~1 HEAD       # 1 file changed: the config, +6 lines
$ git diff HEAD~1 HEAD -- agent/    # nothing at all
```

### Step 4: Looking at the raw messages, once

MCP sounds mysterious until you watch it. [capture_wire.py](capture_wire.py) talks to a
server with no SDK at all — just JSON lines down a pipe — and saves every message with a
note on each field. It is plain JSON-RPC:

```json
{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
```

### Step 5: Writing a tool description *as a prompt*

A tool's description isn't documentation — it's the instructions the model reads. Ours was
too thin, and the model paid for it.

Asked *"I have 1 kg of cabbage, how much salt?"*, it scaled the recipe so the **salt**
weighed a kilo, and answered **"you need 1000 g of salt"**. The tool did exactly what it
was asked.

Two fixes to that one tool:
- **The description now explains which ingredient to scale by** and names the trap.
- **The error is now recoverable:** instead of `Error 3`, it says what went wrong, which
  ingredient was probably meant, and the exact call to make next.

| Same question, same model | Answer |
|---|---|
| Before | "You need **2 kg of fine sea salt** for 1 kg of cabbage" ❌ |
| After | "For 1 kg of white cabbage, you need **20 g** of fine sea salt" ✅ |

### Tools vs resources

Our server offers three **tools** (things the model chooses to call) and one **resource**
(the dietary-tag table). A resource is context the app attaches because it already knows
it's needed. Making it a tool would waste a step and a model call asking for something we
could just hand over.

---

## What we learned, in plain words

- **Discovery is the whole point.** Once the agent asks "what can you do?" instead of being
  told, a new tool is a config line.
- **The AI runs in the host, never in the server.** If our recipe server called a model
  itself, everyone connecting would inherit our model choice and our bill.
- **Tool descriptions are prompts.** A three-word description cost us a wrong answer
  (2 kg of salt); rewriting it fixed the answer with no change to the agent.
- **Errors should teach, not just fail.** `Error 3` makes a model give up or invent.
  "Here's what's wrong, here's what exists, here's what to call next" lets it fix itself.
- **Someone else's server runs on your machine, with your account.** Convenience and risk
  arrive together — hence the risk note.
- **MCP didn't improve any answer.** It's plumbing, and saying so plainly is part of the job.

---

## Tech stack

| Part | What we used | Why |
|---|---|---|
| Language | **Python 3.13** | |
| MCP | the official **`mcp` Python SDK** (v2.3), `MCPServer` for servers, `ClientSession` for the client | The standard itself; no bespoke protocol code |
| Transport | **stdio** — each server is a child process, JSON lines over its pipes | Simplest transport, and the one local tools actually use |
| The agent | Our Week 7–8 loop, with the tool list injected | Proves the point: tools are data, not code |
| The AI model | **Qwen2.5-3B-Instruct, quantised**, via llama.cpp on the CPU | Free, offline. Runs in the **host** only |
| Search inside our server | MiniLM embeddings + BM25 from Weeks 4–6 | Already built |
| Proof | **git** | A diff is harder to argue with than a claim |

**Cost: nothing.** Everything runs locally.

---

## Folder layout

```
config/mcp_servers.json          THE ONLY PLACE servers are listed
  mcp_servers.one_server.json    a copy with just our server, for the before/after
  mcp_servers.v1_terse.json      points at the "bad docstring" server
mcp_servers/
  recipe_server.py               OUR server: 3 tools + 1 resource over the recipe cards
  recipe_server_v1.py            the "before" version: three-word docstrings, "Error 3"
  ingredient_server.py           the SECOND server: cups, allergens, substitutes
agent/
  mcp_client.py                  connects, runs tools/list, offers what it found
  agent.py                       the loop — CONTAINS NO TOOL NAMES
  llm.py, llm_local.py           the model (host side)
list_tools.py                    what got discovered, from tools/list
capture_wire.py                  raw JSON-RPC, no SDK, annotated
demo_query.py                    one question, with the server shown for each tool call
error_before_after.py            the docstring/error comparison
run_all.py                       everything in order
results/                         traces, wire.json, tool counts, risk note
```

---

## How to run it

```bash
pip install -r requirements.txt
python run_all.py                      # all five steps, offline, free
```

Individual pieces:

```bash
python list_tools.py                               # what the agent discovers right now
python list_tools.py --config config/mcp_servers.one_server.json   # ...with one server
python capture_wire.py                             # raw JSON-RPC, instant
python demo_query.py "how many cups is 900 g of bread flour?"
python error_before_after.py --tools-only          # the error comparison, instant
git diff HEAD~1 HEAD -- agent/                     # the zero-diff proof (empty)
```

---

## Words you'll see, explained simply

| Term | Meaning |
|---|---|
| **MCP** | Model Context Protocol: a standard way for AI apps to reach tools and data |
| **Host** | The app that runs the AI model and decides what to call. Ours is the agent. |
| **Client** | The piece that holds one connection to one server |
| **Server** | A program offering tools. No AI inside. |
| **Tool** | Something the model can choose to invoke, with named arguments |
| **Resource** | Context the app attaches itself, rather than making the model ask |
| **Discovery** | Asking a server what tools it has (`tools/list`) instead of hard-coding them |
| **JSON-RPC** | The old, boring message format MCP uses: `{"jsonrpc":"2.0","method":...}` |
| **stdio transport** | Talking to a server through its standard input and output |
| **Recoverable error** | A failure explained well enough that the model can fix its own call |
| **Least privilege** | Giving a tool the least access it needs, so a problem stays small |
