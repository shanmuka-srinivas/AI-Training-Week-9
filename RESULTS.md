# Week 9, Track B (Recipes & food) — MCP

**Task:** connect the agent to a tool over MCP so it *discovers* the tool instead of me
wiring it in, then build my own MCP server another agent could call, and bolt on a second
server without touching the agent.

| Mentor check | Answer |
|---|---|
| Tools used through MCP, discovered not hard-coded? | **Yes.** `agent/agent.py` contains no tool name at all; the list comes from `tools/list` at start-up |
| Second tool added without changing agent code? | **Yes: `git diff HEAD~1 HEAD -- agent/` is empty.** One file changed, the config, +6 lines |
| Own server another person's agent could call? | **Yes:** `mcp_servers/recipe_server.py`, standard stdio MCP, 3 tools + 1 resource |
| Where the model runs, in plain words? | **In the host, never in the server** — see §3 |

Everything runs offline on the local Qwen model. No API key, no cost.

---

## 1. Tool discovery: 3 → 6, from a config edit

Taken from `tools/list`, not from my notes
([tools_before.txt](results/tools_before.txt), [tools_after.txt](results/tools_after.txt)):

| | servers | tools | names |
|---|---|---|---|
| **before** | 1 | **3** | `search_recipes`, `get_recipe_section`, `scale_recipe` |
| **after** | 2 | **6** | the three above + `ingredient_info`, `grams_to_cups`, `substitutes_for` |

Each server reports itself in the handshake: `recipe-cards v1.0.0` and `ingredient-db
v0.4.2`, both speaking MCP `2025-11-25`.

## 2. The zero-diff proof

```
$ git diff --stat HEAD~1 HEAD
 config/mcp_servers.json | 6 ++++++
 1 file changed, 6 insertions(+)

$ git diff HEAD~1 HEAD -- agent/
(nothing)
```

[results/agent_diff.txt](results/agent_diff.txt) is empty on purpose: that *is* the
deliverable. The six added lines are the new server's entry in
[config/mcp_servers.json](config/mcp_servers.json).

**And the agent really used the new server.** Asked *"scaling the pizza dough to 1500 g of
Tipo 00 flour — how many US cups, and does the flour carry an allergen?"*, the trace shows
([results/trace_two_servers.json](results/trace_two_servers.json)):

```
step 1  ACT  grams_to_cups({"name": "strong white bread flour", "grams": 1500})   [server: ingredient-db]
step 2  ACT  ingredient_info({"name": "strong white bread flour"})                [server: ingredient-db]
step 3  FINAL  1500 grams ... is approximately 11.81 US cups, and it carries the allergen gluten.
```

**Honest flaw in that run:** the question was about **Tipo 00** flour, and the model looked
up *strong white bread flour* instead. The database holds both (Tipo 00 is 116 g per cup,
so the true answer is 12.93 cups, not 11.81). MCP delivered the tool correctly; the model
picked the wrong argument. A `did_you_mean` on near-miss names would catch it, and that is
on my list rather than claimed as done.

## 3. Where the model runs

**The model runs in the host — our agent process — and nowhere else.**

- `agent/agent.py` is the only file that calls a model. It decides *which* tool to call.
- `mcp_servers/*.py` contain no AI at all: they read markdown files and divide numbers.
  A server that called a model itself would be making the model choice, and paying for it,
  on behalf of everyone who connects to it.
- The servers never learn which model is asking. The ingredient server would answer a
  Claude-based agent, a Gemini one, or a script, identically.

Captured end to end in [results/wire.json](results/wire.json), with a note on every
top-level field. The short version of the wire:

| message | direction | what it does |
|---|---|---|
| `initialize` | host → server | agree a protocol version, swap names and capabilities |
| `notifications/initialized` | host → server | "ready" — a notification, so it has no `id` and gets no reply |
| `tools/list` | host → server | **discovery**: name, description and JSON Schema for every tool |
| `tools/call` | host → server | run one tool with arguments |

One detail worth reading twice: the deliberately failing call comes back with
**`isError: false`** and the problem described *inside* the result. The tool chose to
return a readable failure rather than raise, so the model can act on it. An exception
would have become a JSON-RPC `error` and killed the step.

## 4. Docstring-as-prompt and a recoverable error

A real failure from the first live run: asked *"I have 1 kg of cabbage, how much salt?"*,
the model called `scale_recipe(R-106, "fine sea salt", 1000)` — scaling the recipe so the
**salt** weighed a kilo — and answered **"you need 1000 g of fine sea salt"**. The tool did
exactly what it was told. The bug was in my tool description.

Two changes to **one tool**, nothing else
([results/error_before_after.md](results/error_before_after.md)):

1. **The docstring became a prompt.** It now says `target_grams` applies to the ingredient
   you name, tells the model to pass the ingredient the cook *has*, and names the trap
   ("scaling by the salt multiplies the recipe by 143").
2. **One error path became recoverable.** An absurd scale no longer succeeds silently; it
   returns what is wrong, which ingredient was probably meant, and the exact call to make
   next.

**Same question, same model, same agent:**

| | final answer | correct? |
|---|---|---|
| **BEFORE** (`"""Scale a recipe."""`, `{"error": "Error 3"}`) | "You need **2 kg of fine sea salt** for 1 kg of white cabbage" | no |
| **AFTER** (docstring as prompt, recoverable errors) | "For 1 kg of white cabbage, you need **20 g** of fine sea salt" | **yes** |

In the BEFORE run the model compounded the error, turning 1000 g into 2 kg. In the AFTER
run the better description meant it never made the mistake, so the new error path never
fired — so I also sent the identical bad calls straight to both servers, with no model
involved:

| bad call | BEFORE | AFTER |
|---|---|---|
| scale by the salt | silently returns a 143× recipe (50 kg of cabbage) | `warning` + `likely_intended` + `next_step` with the exact call |
| ingredient not in the recipe | `{"error": "Error 3"}` | names the problem, lists the four real ingredients, says what to call |
| section that doesn't exist | `{"error": "Error 4"}` | `'nutrition' is not a section. Use one of: ingredients, method, allergens, storage, about.` |

## 5. Tools vs resources, a design decision I had to make

The dietary-tag table is exposed as a **resource** (`recipe://dietary-tags`), not a tool.
It is small, it never changes mid-conversation, and the app should hand it over with the
question. Making it a tool would mean the model spending a step, and a model call, asking
for something we could simply have attached.

Rule of thumb I'm taking from this: **tools are what the model decides to invoke;
resources are context the app attaches.**

## 6. Supply-chain risk note

Five lines, in [results/risk_note.md](results/risk_note.md). The short version: the
ingredient server is someone else's code that *we* launch, so it runs with our user
account, our files and our network — the MCP boundary limits what our agent asks it, not
what the process can touch. Ship it read-only and pinned; don't give it network access or
private user data until it is sandboxed with its own credentials.

## 7. What I would not claim

- **Two servers, one machine, stdio only.** No remote MCP, no auth, no OAuth. Those are the
  parts where the security story gets real, and they are untested here.
- **The bonus (a gateway with an audit line and a scoped token) is not built.** The design
  is obvious — one front door, fan out, log caller/tool/args, deny a tool per token — but
  I am not claiming an untested design as a result.
- **One query per scenario.** Enough to prove the plumbing; not a reliability measurement.
- **MCP changed nothing about answer quality**, and that is the honest framing for a
  client. It is plumbing: the win is that a tool another team wrote became available to our
  agent with a six-line config change, and that our recipe server can now be called by
  anyone else's agent.

## Reproduce

```bash
pip install -r requirements.txt
python run_all.py                      # all five steps, offline
git diff HEAD~1 HEAD -- agent/         # the zero-diff proof (empty)
```
