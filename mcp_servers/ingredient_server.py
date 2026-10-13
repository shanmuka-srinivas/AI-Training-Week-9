"""
THE SECOND SERVER: an ingredient database.

This stands in for a server another team runs. Our agent does not know it exists
until it appears in config/mcp_servers.json, and adding it must not change a
single line of agent code — that is the whole point of the week.

It knows things our recipe cards do not: what an ingredient weighs per cup, what
allergens it carries, and what you can swap it for. That is a genuinely different
dataset, not a copy of ours.

    python mcp_servers/ingredient_server.py     (speaks MCP over stdio)

No AI in here either. It is a lookup table and a division.
"""

from mcp.server.mcpserver import MCPServer

server = MCPServer(
    name="ingredient-db",
    version="0.4.2",
    instructions="Reference data about individual ingredients: weights, allergens, substitutes.",
)

# grams per US cup, allergen group, and swaps. Kitchen-reference figures.
INGREDIENTS = {
    "strong white bread flour": {"g_per_cup": 127, "allergens": ["gluten"],
                                 "substitutes": [("plain flour", "1:1, a slacker dough and less chew")]},
    "plain flour": {"g_per_cup": 125, "allergens": ["gluten"],
                    "substitutes": [("strong white bread flour", "1:1, chewier crumb")]},
    "tipo 00 flour": {"g_per_cup": 116, "allergens": ["gluten"],
                      "substitutes": [("plain flour", "1:1, softer base, less stretch")]},
    "wholegrain rye flour": {"g_per_cup": 102, "allergens": ["gluten"], "substitutes": []},
    "wholegrain buckwheat flour": {"g_per_cup": 120, "allergens": [],
                                   "substitutes": [("brown rice flour", "1:1, milder and paler")]},
    "brown rice flour": {"g_per_cup": 158, "allergens": [], "substitutes": []},
    "water": {"g_per_cup": 237, "allergens": [], "substitutes": []},
    "fine sea salt": {"g_per_cup": 288, "allergens": [],
                      "substitutes": [("table salt", "use 0.8x by volume, it packs denser")]},
    "coarse sea salt": {"g_per_cup": 221, "allergens": [], "substitutes": []},
    "caster sugar": {"g_per_cup": 200, "allergens": [], "substitutes": []},
    "light tahini": {"g_per_cup": 240, "allergens": ["sesame"],
                     "substitutes": [("sunflower seed butter", "1:1, nut and sesame free, slightly sweeter")]},
    "cultured buttermilk": {"g_per_cup": 245, "allergens": ["milk"],
                            "substitutes": [("milk plus lemon juice", "1 cup milk + 1 tbsp lemon, rest 10 min")]},
    "melted butter": {"g_per_cup": 227, "allergens": ["milk"],
                      "substitutes": [("neutral oil", "0.8x by weight, no dairy")]},
    "extra virgin olive oil": {"g_per_cup": 216, "allergens": [], "substitutes": []},
    "whole egg": {"g_per_cup": 243, "allergens": ["egg"], "substitutes": []},
    "gochugaru chilli flakes": {"g_per_cup": 96, "allergens": [], "substitutes": []},
    "anchovy fish sauce": {"g_per_cup": 270, "allergens": ["fish"],
                           "substitutes": [("kelp and shiitake stock", "1:1, vegan, less savoury depth")]},
    "salted shrimp": {"g_per_cup": 250, "allergens": ["crustacean shellfish"], "substitutes": []},
    "psyllium husk, whole": {"g_per_cup": 80, "allergens": [], "substitutes": []},
    "napa cabbage": {"g_per_cup": 70, "allergens": [], "substitutes": []},
    "white cabbage": {"g_per_cup": 89, "allergens": [], "substitutes": []},
    "caraway seed": {"g_per_cup": 96, "allergens": [], "substitutes": []},
    "dried chickpeas": {"g_per_cup": 200, "allergens": [], "substitutes": []},
}


def _find(name):
    key = " ".join(str(name).lower().split())
    if key in INGREDIENTS:
        return key, INGREDIENTS[key]
    partial = [k for k in INGREDIENTS if key in k or k in key]
    if len(partial) == 1:
        return partial[0], INGREDIENTS[partial[0]]
    return None, partial


@server.tool()
def ingredient_info(name: str) -> dict:
    """Look up reference facts about a single ingredient: allergens and weight per cup.

    Use this for questions about an ingredient itself rather than about a recipe, for
    example "is tahini a nut?" or "what allergen is in buttermilk". For how much of an
    ingredient a recipe needs, use the recipe tools instead.
    """
    key, found = _find(name)
    if key is None:
        return {"error": f"'{name}' is not in the ingredient database.",
                "did_you_mean": found[:5] if found else [],
                "next_step": "Try one of the suggestions, or the plainest form of the name, e.g. 'water'."}
    return {"ingredient": key, "grams_per_cup": found["g_per_cup"],
            "allergens": found["allergens"] or ["none recorded"]}


@server.tool()
def grams_to_cups(name: str, grams: float) -> dict:
    """Convert a weight of one ingredient into US cups, using that ingredient's density.

    Flour and water weigh very different amounts per cup, so this needs the ingredient
    name as well as the grams: grams_to_cups("strong white bread flour", 900).
    """
    key, found = _find(name)
    if key is None:
        return {"error": f"'{name}' is not in the ingredient database, so its density is unknown.",
                "did_you_mean": found[:5] if found else [],
                "next_step": "Call ingredient_info first to check the exact name."}
    try:
        grams = float(grams)
    except (TypeError, ValueError):
        return {"error": f"grams must be a number, got '{grams}'."}
    cups = grams / found["g_per_cup"]
    return {"ingredient": key, "grams": grams, "cups": round(cups, 2),
            "note": f"based on {found['g_per_cup']} g per cup"}


@server.tool()
def substitutes_for(name: str) -> dict:
    """List what an ingredient can be swapped for, with the ratio and the catch.

    Use when the cook says they don't have something. Returns an empty list when the
    database records no safe swap, which means "don't guess one".
    """
    key, found = _find(name)
    if key is None:
        return {"error": f"'{name}' is not in the ingredient database.",
                "did_you_mean": found[:5] if found else []}
    if not found["substitutes"]:
        return {"ingredient": key, "substitutes": [],
                "note": "No substitute is recorded for this ingredient. Say so rather than inventing one."}
    return {"ingredient": key,
            "substitutes": [{"use": swap, "how": how} for swap, how in found["substitutes"]]}


if __name__ == "__main__":
    server.run(transport="stdio")
