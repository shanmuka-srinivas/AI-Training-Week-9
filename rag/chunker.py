"""
The structure-aware chunker that won in Week 3. It is NOT changed this week.

Rules:
  * an ingredient row is never split from its table header
  * a paragraph of method prose is never cut in half
  * every chunk starts with a 3-line "stamp" naming the recipe and section

    Recipe: Traditional Napa Cabbage Kimchi (R-104)
    Section: Ingredients
    Cuisine: korean | Dietary tags: gluten-free, dairy-free, ...

The stamp is part of the text that gets searched. That matters for this week:
it is why the recipe code "R-104" is findable at all.
"""

import re
from dataclasses import dataclass

from .config import METHOD_CHUNK_TARGET, ROWS_PER_TABLE_CHUNK

STAMP_PREFIXES = ("Recipe:", "Section:", "Cuisine:")


@dataclass
class Chunk:
    chunk_id: str        # e.g. "R-104::ingredients::0"
    recipe_id: str
    recipe_title: str
    section: str
    source_file: str
    text: str            # stamp + body: what gets searched

    @property
    def body(self):
        """The chunk without its stamp: the part that actually came from the card."""
        return "\n".join(
            line for line in self.text.splitlines() if not line.startswith(STAMP_PREFIXES)
        ).strip()


def _slug(section_name):
    lowered = section_name.lower()
    for short in ("ingredients", "method", "allergen"):
        if lowered.startswith(short[:6]):
            return short
    return re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")


def _is_table_row(line):
    s = line.strip()
    return s.startswith("|") and s.endswith("|")


def _is_separator(line):
    return bool(re.fullmatch(r"\|[\s\-:|]+\|", line.strip()))


def _make(card, section, index, body):
    stamp = (
        f"Recipe: {card.title} ({card.recipe_id})\n"
        f"Section: {section}\n"
        f"Cuisine: {card.cuisine} | Dietary tags: {', '.join(card.dietary_tags)}"
    )
    return Chunk(
        chunk_id=f"{card.recipe_id}::{_slug(section)}::{index}",
        recipe_id=card.recipe_id,
        recipe_title=card.title,
        section=section,
        source_file=card.source_file,
        text=stamp + "\n\n" + body.strip(),
    )


def _table_chunks(card, section, text):
    header = separator = None
    rows, intro = [], []
    for line in text.splitlines():
        if _is_table_row(line):
            if header is None:
                header = line.strip()
            elif separator is None and _is_separator(line):
                separator = line.strip()
            else:
                rows.append(line.strip())
        elif line.strip():
            intro.append(line.strip())

    if header is None or not rows:
        return _prose_chunks(card, section, text)

    chunks = []
    for i, start in enumerate(range(0, len(rows), ROWS_PER_TABLE_CHUNK)):
        body = intro + ([""] if intro else []) + [header, separator or "|---|---|---|"]
        body += rows[start : start + ROWS_PER_TABLE_CHUNK]
        chunks.append(_make(card, section, i, "\n".join(body)))
    return chunks


def _prose_chunks(card, section, text):
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, current, length = [], [], 0
    for paragraph in paragraphs:
        if current and length + len(paragraph) > METHOD_CHUNK_TARGET:
            chunks.append(_make(card, section, len(chunks), "\n\n".join(current)))
            current, length = [], 0
        current.append(paragraph)
        length += len(paragraph)
    if current:
        chunks.append(_make(card, section, len(chunks), "\n\n".join(current)))
    return chunks


def chunk_card(card):
    chunks = [_make(card, "Overview", 0, f"Yield: {card.yield_note}\nHydration: {card.hydration}")]
    for section, text in card.sections.items():
        if not text.strip():
            continue
        if any(_is_table_row(line) for line in text.splitlines()):
            chunks.extend(_table_chunks(card, section, text))
        else:
            chunks.extend(_prose_chunks(card, section, text))
    return chunks


def chunk_cards(cards):
    return [chunk for card in cards for chunk in chunk_card(card)]
