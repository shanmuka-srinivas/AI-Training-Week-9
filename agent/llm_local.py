"""
The local model backend: Qwen2.5-3B-Instruct, quantised (Q4_K_M), run by
llama.cpp on this computer's CPU.

Why it exists: the Gemini free tier allows 20 calls a day and the race needs
hundreds, so the whole race can also run offline, with no API key, no quota and
no bill. The trade-off is real and worth knowing:

    Gemini flash-lite    ~1.5 s per call, costs money, follows instructions well
    local Qwen 3B (Q4)   ~30 s per call, free, and a much smaller model that
                         slips out of the JSON format more often

"Quantised" means the model's numbers are squeezed from 16 bits to about 4, so
it uses ~2 GB instead of ~12 GB and runs several times faster, for a small loss
of quality. Without that, a 3B model on this CPU would take minutes per step.

Cost is still measured in tokens. Dollars are reported as $0.00, because the
only real cost is your own electricity and time.

The model file (~2 GB) downloads once into the usual Hugging Face cache.
"""

import json
import os
import re
import time

REPO = "Qwen/Qwen2.5-3B-Instruct-GGUF"
FILENAME = "qwen2.5-3b-instruct-q4_k_m.gguf"
MODEL_NAME = "Qwen2.5-3B-Instruct Q4_K_M (llama.cpp, local CPU)"
CONTEXT_TOKENS = 8192
MAX_NEW_TOKENS = 250

_llm = None


def _load():
    global _llm
    if _llm is None:
        from huggingface_hub import hf_hub_download
        from llama_cpp import Llama

        previous = os.environ.get("HF_HUB_OFFLINE")
        os.environ["HF_HUB_OFFLINE"] = "0"          # allow the one-off download
        try:
            path = hf_hub_download(REPO, FILENAME)
        finally:
            if previous is not None:
                os.environ["HF_HUB_OFFLINE"] = previous
        _llm = Llama(model_path=path, n_ctx=CONTEXT_TOKENS, n_threads=os.cpu_count() or 4, verbose=False)
    return _llm


def _first_json_object(text):
    """
    Pull the first {...} out of the reply.

    A small model often wraps its JSON in ```json fences or writes a sentence
    first. That's a formatting slip, not a wrong decision, so we fish the object
    out instead of failing the whole step.
    """
    cleaned = re.sub(r"```(?:json)?|```", "", text).strip()
    start = cleaned.find("{")
    if start == -1:
        return None
    depth, in_string, escape = 0, False, False
    for i, char in enumerate(cleaned[start:], start=start):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(cleaned[start : i + 1])
                    return parsed if isinstance(parsed, dict) else None
                except json.JSONDecodeError:
                    return None
    return None


def call_json(prompt, temperature=0.0):
    """
    Same contract as the Gemini backend: (parsed_json_or_None, raw_text, usage).
    `prompt` is either a plain string or a list of chat messages.
    """
    llm = _load()
    messages = prompt if isinstance(prompt, list) else [{"role": "user", "content": prompt}]
    started = time.perf_counter()
    response = llm.create_chat_completion(
        messages=messages,
        temperature=temperature,
        max_tokens=MAX_NEW_TOKENS,
        response_format={"type": "json_object"},
    )
    seconds = time.perf_counter() - started

    usage = response.get("usage", {})
    raw = response["choices"][0]["message"]["content"] or ""
    measurements = {
        "seconds": seconds,
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
        "cost_usd": 0.0,   # runs on your own machine
    }
    return _first_json_object(raw), raw, measurements
