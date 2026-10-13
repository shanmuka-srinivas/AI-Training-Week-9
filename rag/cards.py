"""
Reads a recipe card (a markdown file) into a Python object.

A card looks like:

    # Two-Kilo Country Sourdough
    - recipe_id: R-101
    - cuisine: french
    - dietary_tags: vegan, dairy-free, contains-gluten
    - yield: one 2 kg boule
    - hydration: 75%

    ## Ingredients
    | Ingredient | Weight | Baker's % |
    ...
    ## Method
    ...
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RecipeCard:
    source_file: str
    recipe_id: str
    title: str
    cuisine: str
    dietary_tags: list
    yield_note: str
    hydration: str
    sections: dict = field(default_factory=dict)   # "Ingredients" -> text


def _metadata_block(lines):
    """Pull the "- key: value" lines from the top of the card."""
    metadata = {}
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            break
        if stripped.startswith("- ") and ":" in stripped:
            key, value = stripped[2:].split(":", 1)
            metadata[key.strip().lower()] = value.strip()
    return metadata


def _sections(text):
    """Split the card on its "## Heading" lines, keeping the order."""
    sections = {}
    name, lines = None, []
    for line in text.splitlines():
        if line.startswith("## "):
            if name is not None:
                sections[name] = "\n".join(lines).strip()
            name, lines = line[3:].strip(), []
        elif name is not None:
            lines.append(line)
    if name is not None:
        sections[name] = "\n".join(lines).strip()
    return sections


def load_card(path):
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    title = next((line[2:].strip() for line in lines if line.startswith("# ")), "Untitled")
    metadata = _metadata_block(lines)
    if not metadata.get("recipe_id"):
        raise ValueError(f"{path.name} has no recipe_id")

    return RecipeCard(
        source_file=path.name,
        recipe_id=metadata["recipe_id"],
        title=title,
        cuisine=metadata.get("cuisine", "unknown"),
        dietary_tags=[t.strip() for t in metadata.get("dietary_tags", "").split(",") if t.strip()],
        yield_note=metadata.get("yield", ""),
        hydration=metadata.get("hydration", ""),
        sections=_sections(text),
    )


def load_all_cards(folder):
    return [load_card(p) for p in sorted(Path(folder).glob("*.md"))]
