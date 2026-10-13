"""
Every setting in one place.

All of these were fixed BEFORE the first run and none were tuned afterwards.
The whole point of the week is "change one thing and measure it", and that only
works if nothing else quietly moves.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RECIPES_DIR = PROJECT_ROOT / "data" / "recipes"
RESULTS_DIR = PROJECT_ROOT / "results"

# ---------------------------------------------------------------------------
# Chunking (unchanged from the structure-aware chunker shipped in Week 3)
# ---------------------------------------------------------------------------
ROWS_PER_TABLE_CHUNK = 6
METHOD_CHUNK_TARGET = 700

# ---------------------------------------------------------------------------
# Models (both run locally, no API key)
# ---------------------------------------------------------------------------
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"   # same model as Week 3
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"       # appendix only

# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

# The headline number is hit-rate@3, and the answerer reads exactly the top 3
# chunks, so "fetched" always means "in the top 3".
TOP_K = 3

# We also keep a deeper list for MRR and for the inspection view, so you can
# see WHERE the right chunk ended up when it missed the top 3.
DEEP_K = 10

# BM25 keyword search. These are the textbook defaults, not tuned values.
BM25_K1 = 1.5
BM25_B = 0.75

# Reciprocal Rank Fusion. k=60 is the value from the original RRF paper
# (Cormack et al., 2009) and the default almost everywhere. Each search
# contributes its top CANDIDATES_PER_SEARCH results to the fusion.
RRF_K = 60
CANDIDATES_PER_SEARCH = 20

# ---------------------------------------------------------------------------
# Answering (unchanged from Week 3)
# ---------------------------------------------------------------------------
MIN_SCORE_TO_ANSWER = 0.30     # gate 2: the best chunk must be at least this close
MIN_SENTENCE_SCORE = 0.25      # gate 3: the chosen sentence must be at least this close
CHUNK_WEIGHT = 0.45            # how much the chunk's own rank counts when picking a sentence
