"""
BM25 keyword search, written out in full so nothing is hidden in a library.

Meaning search (embeddings) asks "which chunk is ABOUT the same thing?".
Keyword search asks "which chunk USES the same words?". Those are different
questions, and the difference shows up on exact terms: to an embedding model
"R-106" is a meaningless scrap, but to BM25 it is a rare token that appears in
exactly one recipe's chunks, which makes it a very strong signal.

How BM25 scores a chunk for a query, in plain words:

  for every query word that is in the chunk, add up
      rarity of the word       (IDF: a word in few chunks is worth more)
    x how often it appears     (with diminishing returns, controlled by k1)
    / how long the chunk is    (long chunks are penalised a little, controlled by b)
"""

import math
import re
from collections import Counter

from .config import BM25_B, BM25_K1

# Common English words that tell us nothing about what was asked.
STOPWORDS = frozenset("""
a about above after again all also am an and any are as at be because been before
being below between both but by can could did do does doing down during each few
for from further had has have having he her here hers him his how i if in into is
it its itself just me more most my no nor not now of off on once only or other our
out over own same she should so some such than that the their them then there these
they this those through to too under until up very was we were what when where which
while who whom why will with would you your
""".split())

# A token is letters/digits, optionally joined by hyphens or dots, so that
# "R-106", "6.1", "gluten-free" and "00" all survive as whole tokens.
TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[-.][a-z0-9]+)*")


def tokenize(text):
    """
    Lowercase words for BM25.

    A hyphenated token is kept whole AND split into its parts, so a query for
    "R-106" matches the exact code, while "gluten free" still matches
    "gluten-free".
    """
    tokens = []
    for token in TOKEN_PATTERN.findall(text.lower()):
        if token in STOPWORDS:
            continue
        tokens.append(token)
        if "-" in token:
            tokens.extend(part for part in token.split("-") if part and part not in STOPWORDS)
    return tokens


class BM25Index:
    def __init__(self, documents):
        self.doc_tokens = [Counter(tokenize(doc)) for doc in documents]
        self.doc_lengths = [sum(counts.values()) for counts in self.doc_tokens]
        self.avg_length = sum(self.doc_lengths) / len(self.doc_lengths)

        # How many chunks contain each word at least once.
        document_frequency = Counter()
        for counts in self.doc_tokens:
            document_frequency.update(counts.keys())

        n = len(documents)
        # The "+1 inside the log" form, which never goes negative.
        self.idf = {
            word: math.log(1 + (n - df + 0.5) / (df + 0.5))
            for word, df in document_frequency.items()
        }

    def scores(self, query):
        """One BM25 score per chunk, in the same order the chunks were given."""
        query_words = tokenize(query)
        results = []
        for counts, length in zip(self.doc_tokens, self.doc_lengths):
            score = 0.0
            for word in query_words:
                tf = counts.get(word, 0)
                if tf == 0:
                    continue
                norm = tf + BM25_K1 * (1 - BM25_B + BM25_B * length / self.avg_length)
                score += self.idf[word] * tf * (BM25_K1 + 1) / norm
            results.append(score)
        return results
