"""
Every way this project can fetch chunks for a question.

    dense    BEFORE.  Meaning search only (embeddings + cosine similarity).
    hybrid   AFTER.   Meaning search + BM25 keyword search, merged with RRF.
                      This is the ONE change being measured.

The appendix measures three other single changes, each on its own against
"dense", purely for learning. They are not stacked and not shipped:

    rerank   dense top 20 -> cross-encoder re-scores them -> top 3
    mmr      dense top 20 -> Maximal Marginal Relevance picks 3 varied chunks
    rewrite  rule-based query rewrite -> dense

Every retriever returns the same thing: a ranked list of Hit objects. The
answerer and the evaluation never know which retriever produced them.
"""

import re
from dataclasses import dataclass, field

import numpy as np

from .bm25 import BM25Index
from .config import CANDIDATES_PER_SEARCH, RRF_K
from .embedder import cross_encoder, embed


@dataclass
class Hit:
    rank: int
    chunk: object
    score: float
    detail: dict = field(default_factory=dict)   # e.g. dense rank / bm25 rank, for the inspection view


class SearchIndex:
    """All chunks, their embeddings, and a BM25 index over the same text."""

    def __init__(self, chunks):
        self.chunks = chunks
        self.vectors = embed(c.text for c in chunks)
        self.bm25 = BM25Index([c.text for c in chunks])
        self._dense_cache = {}

    # ---- the two basic searches ------------------------------------------

    def dense_ranking(self, question):
        """(chunk index, cosine similarity) for every chunk, best first."""
        if question not in self._dense_cache:
            q = embed([question])[0]
            sims = self.vectors @ q
            order = np.argsort(-sims, kind="stable")
            self._dense_cache[question] = [(int(i), float(sims[i])) for i in order]
        return self._dense_cache[question]

    def bm25_ranking(self, question):
        """(chunk index, BM25 score) for every chunk that shares a word, best first."""
        scores = self.bm25.scores(question)
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
        return [(i, scores[i]) for i in order if scores[i] > 0]

    def cosine(self, question, chunk):
        """Cosine similarity of one chunk to the question (used by the answerer)."""
        index = self.chunks.index(chunk)
        return dict(self.dense_ranking(question))[index]


# ---------------------------------------------------------------------------
# BEFORE: dense only
# ---------------------------------------------------------------------------

def dense(index, question, k):
    ranking = index.dense_ranking(question)[:k]
    return [Hit(rank=r + 1, chunk=index.chunks[i], score=s) for r, (i, s) in enumerate(ranking)]


# ---------------------------------------------------------------------------
# AFTER: hybrid (dense + BM25, fused with Reciprocal Rank Fusion)
# ---------------------------------------------------------------------------

def hybrid(index, question, k):
    """
    Reciprocal Rank Fusion, in one line:

        fused score = 1 / (60 + rank in dense list) + 1 / (60 + rank in BM25 list)

    It uses only the RANK from each search, never the raw score. That is the
    whole trick: a cosine similarity of 0.62 and a BM25 score of 14.3 are on
    completely different scales and cannot be added, but "2nd place" and
    "5th place" can. A chunk near the top of both lists wins; a chunk at the
    top of only one list still gets a good score.
    """
    dense_top = index.dense_ranking(question)[:CANDIDATES_PER_SEARCH]
    bm25_top = index.bm25_ranking(question)[:CANDIDATES_PER_SEARCH]

    fused, detail = {}, {}
    for name, ranking in (("dense", dense_top), ("bm25", bm25_top)):
        for rank, (i, _) in enumerate(ranking, start=1):
            fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + rank)
            detail.setdefault(i, {})[f"{name}_rank"] = rank

    order = sorted(fused, key=lambda i: (-fused[i], i))[:k]
    return [
        Hit(rank=r + 1, chunk=index.chunks[i], score=fused[i], detail=detail[i])
        for r, i in enumerate(order)
    ]


# ---------------------------------------------------------------------------
# Appendix only: three other single changes, each measured alone
# ---------------------------------------------------------------------------

def rerank(index, question, k):
    """Dense fetches 20 candidates; a cross-encoder reads question+chunk together and re-scores."""
    candidates = index.dense_ranking(question)[:CANDIDATES_PER_SEARCH]
    pairs = [(question, index.chunks[i].text) for i, _ in candidates]
    scores = cross_encoder().predict(pairs)
    order = sorted(range(len(candidates)), key=lambda j: -float(scores[j]))[:k]
    return [
        Hit(rank=r + 1, chunk=index.chunks[candidates[j][0]], score=float(scores[j]),
            detail={"dense_rank": j + 1})
        for r, j in enumerate(order)
    ]


def mmr(index, question, k, lambda_=0.7):
    """
    Maximal Marginal Relevance: pick chunks that are relevant AND not
    near-duplicates of chunks already picked.
    """
    candidates = [i for i, _ in index.dense_ranking(question)[:CANDIDATES_PER_SEARCH]]
    relevance = dict(index.dense_ranking(question))
    chosen = []
    while candidates and len(chosen) < k:
        def value(i):
            redundancy = max((float(index.vectors[i] @ index.vectors[j]) for j in chosen), default=0.0)
            return lambda_ * relevance[i] - (1 - lambda_) * redundancy
        best = max(candidates, key=value)
        chosen.append(best)
        candidates.remove(best)
    return [Hit(rank=r + 1, chunk=index.chunks[i], score=relevance[i]) for r, i in enumerate(chosen)]


# Casual words people type, mapped to the words the cards actually use.
REWRITE_SYNONYMS = {
    "bicarb": "bicarbonate of soda",
    "kraut": "sauerkraut",
    "temp": "temperature",
    "gf": "gluten-free",
}


def rewrite_query(index, question):
    """
    A deterministic query rewrite (no LLM):
      1. swap casual words for the words used on the cards
      2. replace a recipe code like "R-106" with the recipe's full title
    """
    titles = {c.recipe_id: c.recipe_title for c in index.chunks}
    text = question
    for casual, formal in REWRITE_SYNONYMS.items():
        text = re.sub(rf"\b{casual}\b", formal, text, flags=re.IGNORECASE)
    text = re.sub(
        r"\bR-\d{3}\b",
        lambda m: f"{titles.get(m.group(0).upper(), m.group(0))} ({m.group(0)})",
        text,
        flags=re.IGNORECASE,
    )
    return text


def rewrite(index, question, k):
    rewritten = rewrite_query(index, question)
    hits = dense(index, rewritten, k)
    for hit in hits:
        hit.detail["rewritten_query"] = rewritten
    return hits


RETRIEVERS = {
    "dense": dense,
    "hybrid": hybrid,
    "rerank": rerank,
    "mmr": mmr,
    "rewrite": rewrite,
}
