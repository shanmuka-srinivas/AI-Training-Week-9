"""
OUR OWN MCP SERVER, VERSION 1 — kept only as the "before" in the write-up.

Same code as recipe_server.py, with two things deliberately bad:
  * the tool docstrings are three words long, so the model has to guess how to
    use them;
  * failures come back as "Error 3", which tells the model nothing it can act on.

See results/error_before_after.md for what that costs. The real server is
recipe_server.py.

Original header follows.

OUR OWN MCP SERVER: the recipe cards.

This exposes one real capability of the app we have been building since Week 3 —
reading and rescaling recipe cards — in a way ANY MCP-speaking agent can use,
not just ours.

    python mcp_servers/recipe_server.py        (speaks MCP over stdio)

WHERE THE MODEL RUNS: not here. This server has no AI in it at all. It reads
markdown files and does arithmetic. The host (our agent) is the only thing that
calls a model. A server that called a model itself would be doing the host's
job, and nobody connecting to it could choose or pay for that model.

TOOLS vs RESOURCES, which is a real design decision:
  * TOOLS are things the model decides to invoke: search, read a section, rescale.
  * RESOURCES are context the app attaches because it already knows it is needed.
    The dietary-tag table is exposed as a resource, not a tool, because an app
    should hand that over with the question rather than make the model go and
    ask for it.
"""

import re
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rag.cards import load_all_cards  # noqa: E402

CARDS = {c.recipe_id: c for c in load_all_cards(ROOT / "data" / "recipes")}

server = MCPServer(
    name="recipe-cards",
    version="0.9.0-terse",
    instructions="Read and rescale the recipe cards held by this kitchen.",
)


def _flat(text):
    return " ".join(str(text).split())


@server.tool()
def search_recipes(query: str, dietary_tag: str | None = None) -> dict:
    """Search recipes."""
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2]
    scored = []
    for card in CARDS.values():
        haystack = (card.title + " " + card.cuisine + " " + " ".join(card.sections.values())).lower()
        score = sum(haystack.count(w) for w in words)
        if score and (dietary_tag is None or dietary_tag.lower() in [t.lower() for t in card.dietary_tags]):
            scored.append((score, card))
    scored.sort(key=lambda pair: -pair[0])
    results = [{"recipe_id": c.recipe_id, "title": c.title, "dietary_tags": c.dietary_tags}
               for _, c in scored[:5]]
    if not results:
        tags = sorted({t for c in CARDS.values() for t in c.dietary_tags})
        return {"results": [],
                "hint": f"Nothing matched '{query}'"
                        + (f" with tag '{dietary_tag}'. Tags in use: {', '.join(tags)}." if dietary_tag else ".")}
    return {"results": results}


@server.tool()
def get_recipe_section(recipe_id: str, section: str) -> dict:
    """Get a recipe section."""
    card = CARDS.get(str(recipe_id).upper())
    if card is None:
        return {"error": "Error 2"}

    section = str(section).lower().strip()
    if section == "overview":
        return {"recipe_id": card.recipe_id, "title": card.title, "cuisine": card.cuisine,
                "dietary_tags": card.dietary_tags, "yield": card.yield_note}
    prefixes = {"ingredients": "ingredient", "method": "method", "allergens": "allergen",
                "storage": "storage", "about": "about"}
    if section not in prefixes:
        return {"error": "Error 4"}
    for name, text in card.sections.items():
        if name.lower().startswith(prefixes[section]):
            return {"recipe_id": card.recipe_id, "title": card.title, "section": name, "text": text.strip()}
    return {"error": f"{card.title} has no {section} section. It has: "
                     f"{', '.join(card.sections)}."}


def _ingredient_rows(card):
    rows = []
    for name, text in card.sections.items():
        if not name.lower().startswith("ingredient"):
            continue
        for line in text.splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2 and not cells[0].lower().startswith("total"):
                match = re.fullmatch(r"([\d.]+)\s*g", cells[1])
                if match:
                    rows.append((cells[0], float(match.group(1))))
    return rows


def _fmt(grams):
    return f"{grams:.1f} g" if grams < 10 else f"{round(grams)} g"


@server.tool()
def scale_recipe(recipe_id: str, ingredient: str, target_grams: float) -> dict:
    """Scale a recipe."""
    card = CARDS.get(str(recipe_id).upper())
    if card is None:
        return {"error": "Error 2"}
    rows = _ingredient_rows(card)
    words = [w for w in re.findall(r"[a-z]+", str(ingredient).lower()) if len(w) > 2]
    matches = [(n, g) for n, g in rows if words and all(w in n.lower() for w in words)]
    if not matches:
        # A RECOVERABLE error: say what went wrong, what does exist, and what to do next,
        # so the model can fix its own call instead of giving up or inventing a number.
        return {"error": "Error 3"}
    try:
        target = float(target_grams)
    except (TypeError, ValueError):
        return {"error": "Error 5"}

    base_name, base_grams = matches[0]
    factor = target / base_grams
    return {
        "recipe_id": card.recipe_id,
        "title": card.title,
        "scaled_so_that": f"{base_name} = {_fmt(target)} (card says {_fmt(base_grams)})",
        "factor": round(factor, 3),
        "scaled_ingredients": [f"{n}: {_fmt(g * factor)}" for n, g in rows],
    }


@server.resource("recipe://dietary-tags")
def dietary_tags() -> str:
    """The dietary tag of every recipe.

    A RESOURCE, not a tool, on purpose: this is small, it never changes during a
    conversation, and an app should attach it rather than make the model ask.
    """
    lines = ["recipe_id | title | dietary tags"]
    for card in sorted(CARDS.values(), key=lambda c: c.recipe_id):
        lines.append(f"{card.recipe_id} | {card.title} | {', '.join(card.dietary_tags)}")
    return "\n".join(lines)


if __name__ == "__main__":
    server.run(transport="stdio")
